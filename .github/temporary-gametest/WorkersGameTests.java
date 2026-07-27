package com.talhanation.workers.gametest;

import com.talhanation.workers.entities.workarea.StorageArea;
import com.talhanation.workers.init.ModEntityTypes;
import net.minecraft.core.BlockPos;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.world.Container;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.block.Blocks;
import net.neoforged.fml.ModList;
import net.neoforged.neoforge.gametest.GameTestHolder;
import net.neoforged.neoforge.gametest.PrefixGameTestTemplate;

import java.util.List;
import java.util.UUID;

@GameTestHolder("workers")
@PrefixGameTestTemplate(false)
public final class WorkersGameTests {
    private static final UUID TEST_OWNER = UUID.fromString("00000000-0000-0000-0000-000000000001");

    private WorkersGameTests() {
    }

    @GameTest(templateNamespace = "minecraft", template = "empty", timeoutTicks = 40)
    public static void requiredModsLoad(GameTestHelper helper) {
        helper.assertTrue(ModList.get().isLoaded("recruits"), "Recruits must load");
        helper.assertTrue(ModList.get().isLoaded("workers"), "Workers must load");
        helper.succeed();
    }

    @GameTest(templateNamespace = "minecraft", template = "empty", timeoutTicks = 80)
    public static void serverEntityTypesInstantiate(GameTestHelper helper) {
        List<EntityType<?>> types = List.of(
                ModEntityTypes.STORAGEAREA.get(), ModEntityTypes.BUILDAREA.get(),
                ModEntityTypes.FARMER.get(), ModEntityTypes.MERCHANT.get(),
                ModEntityTypes.COURIER.get());
        for (EntityType<?> type : types) {
            Entity entity = type.create(helper.getLevel());
            helper.assertTrue(entity != null, "Entity type failed to instantiate: " + type);
        }
        helper.succeed();
    }

    @GameTest(templateNamespace = "minecraft", template = "empty", timeoutTicks = 80)
    public static void storageAreaNbtRoundTrip(GameTestHelper helper) {
        StorageArea storage = createStorage(helper, new BlockPos(1, 1, 1), 1);
        storage.setStorageTypes(8);
        CompoundTag saved = storage.saveWithoutId(new CompoundTag());
        helper.assertValueEqual(saved.getInt("StorageTypes"), 8, "StorageTypes must be saved");

        StorageArea restored = ModEntityTypes.STORAGEAREA.get().create(helper.getLevel());
        helper.assertTrue(restored != null, "Restored StorageArea failed to instantiate");
        restored.load(saved);
        helper.assertValueEqual(restored.getStorageMask(restored.getStorageTypes()), 8,
                "StorageTypes must survive NBT reload");
        helper.succeed();
    }

    @GameTest(templateNamespace = "minecraft", template = "empty", timeoutTicks = 100)
    public static void storageAreaBridgesChestInventory(GameTestHelper helper) {
        BlockPos chestRelative = new BlockPos(1, 1, 1);
        helper.setBlock(chestRelative, Blocks.CHEST);
        StorageArea storage = createStorage(helper, chestRelative, 1);
        addStorage(helper, storage);
        storage.scanStorageBlocks();

        Container container = storage;
        helper.assertValueEqual(container.getContainerSize(), 27,
                "StorageArea must expose the chest inventory");
        container.setItem(0, new ItemStack(Items.WHEAT, 60));
        helper.assertValueEqual(container.getItem(0).getCount(), 60,
                "StorageArea must write through to the chest");
        container.setChanged();
        helper.succeed();
    }

    @GameTest(templateNamespace = "minecraft", template = "empty", timeoutTicks = 100)
    public static void storageAreaSplitsStacksAndDecreasesOnRemoval(GameTestHelper helper) {
        BlockPos chestRelative = new BlockPos(1, 1, 1);
        helper.setBlock(chestRelative, Blocks.CHEST);
        StorageArea storage = createStorage(helper, chestRelative, 1);
        addStorage(helper, storage);
        storage.scanStorageBlocks();

        storage.setItem(0, new ItemStack(Items.WHEAT, 60));
        ItemStack remainder = insert(storage, new ItemStack(Items.WHEAT, 10));
        helper.assertTrue(remainder.isEmpty(), "All wheat must fit in the storage area");
        helper.assertValueEqual(storage.getItem(0).getCount(), 64,
                "The existing stack must fill to 64");
        helper.assertValueEqual(storage.getItem(1).getCount(), 6,
                "The remaining six wheat must use the next slot");

        ItemStack removed = storage.removeItem(0, 4);
        helper.assertValueEqual(removed.getCount(), 4, "Exactly four wheat must be removed");
        helper.assertValueEqual(storage.getItem(0).getCount(), 60,
                "Removing wheat must decrease the underlying chest stack");
        helper.succeed();
    }

    @GameTest(templateNamespace = "minecraft", template = "empty", timeoutTicks = 120)
    public static void storageAreaContinuesIntoAnotherChest(GameTestHelper helper) {
        BlockPos firstChest = new BlockPos(1, 1, 1);
        BlockPos secondChest = new BlockPos(1, 1, 3);
        helper.setBlock(firstChest, Blocks.CHEST);
        helper.setBlock(secondChest, Blocks.CHEST);
        StorageArea storage = createStorage(helper, firstChest, 3);
        addStorage(helper, storage);
        storage.scanStorageBlocks();

        helper.assertValueEqual(storage.getContainerSize(), 54,
                "Two separate chests must expose 54 aggregate slots");
        for (int slot = 0; slot < 27; slot++) {
            storage.setItem(slot, new ItemStack(Items.COBBLESTONE, 64));
        }

        ItemStack remainder = insert(storage, new ItemStack(Items.WHEAT, 6));
        helper.assertTrue(remainder.isEmpty(), "The second chest must accept the remaining wheat");
        helper.assertTrue(storage.getItem(26).is(Items.COBBLESTONE),
                "The final slot of the first chest must remain full");
        helper.assertTrue(storage.getItem(27).is(Items.WHEAT),
                "Insertion must continue into the next chest");
        helper.assertValueEqual(storage.getItem(27).getCount(), 6,
                "The next chest must contain all six wheat");
        helper.succeed();
    }

    @GameTest(templateNamespace = "minecraft", template = "empty", timeoutTicks = 120)
    public static void storageAreaRediscoversChestAfterEntityReload(GameTestHelper helper) {
        BlockPos chestRelative = new BlockPos(1, 1, 1);
        helper.setBlock(chestRelative, Blocks.CHEST);
        StorageArea original = createStorage(helper, chestRelative, 1);
        addStorage(helper, original);
        original.scanStorageBlocks();
        original.setItem(0, new ItemStack(Items.WHEAT, 23));
        original.setChanged();

        CompoundTag saved = original.saveWithoutId(new CompoundTag());
        original.discard();

        StorageArea restored = ModEntityTypes.STORAGEAREA.get().create(helper.getLevel());
        helper.assertTrue(restored != null, "Restored StorageArea failed to instantiate");
        restored.load(saved);
        BlockPos chestAbsolute = helper.absolutePos(chestRelative);
        restored.setPos(chestAbsolute.getX() + 0.5D, chestAbsolute.getY() + 1.0D,
                chestAbsolute.getZ() + 0.5D);
        addStorage(helper, restored);

        helper.assertValueEqual(restored.getContainerSize(), 27,
                "A reloaded StorageArea must rediscover its chest lazily");
        helper.assertTrue(restored.getItem(0).is(Items.WHEAT),
                "Chest contents must remain available after StorageArea reload");
        helper.assertValueEqual(restored.getItem(0).getCount(), 23,
                "Chest item count must survive StorageArea reload");
        helper.succeed();
    }

    private static StorageArea createStorage(GameTestHelper helper, BlockPos chestRelative, int depth) {
        StorageArea storage = ModEntityTypes.STORAGEAREA.get().create(helper.getLevel());
        helper.assertTrue(storage != null, "StorageArea failed to instantiate");
        storage.setPlayerUUID(TEST_OWNER);
        storage.setPlayerName("gametest");
        storage.setWidthSize(1);
        storage.setHeightSize(0);
        storage.setDepthSize(depth);
        BlockPos chestAbsolute = helper.absolutePos(chestRelative);
        storage.setPos(chestAbsolute.getX() + 0.5D, chestAbsolute.getY() + 1.0D,
                chestAbsolute.getZ() + 0.5D);
        return storage;
    }

    private static void addStorage(GameTestHelper helper, StorageArea storage) {
        helper.assertTrue(helper.getLevel().addFreshEntity(storage),
                "StorageArea could not be added to the level");
    }

    private static ItemStack insert(Container container, ItemStack incoming) {
        ItemStack remainder = incoming.copy();
        for (int slot = 0; slot < container.getContainerSize() && !remainder.isEmpty(); slot++) {
            ItemStack existing = container.getItem(slot);
            if (existing.isEmpty() || !ItemStack.isSameItemSameComponents(existing, remainder)) {
                continue;
            }
            int transferable = Math.min(remainder.getCount(), existing.getMaxStackSize() - existing.getCount());
            if (transferable > 0) {
                existing.grow(transferable);
                remainder.shrink(transferable);
                container.setItem(slot, existing);
            }
        }
        for (int slot = 0; slot < container.getContainerSize() && !remainder.isEmpty(); slot++) {
            if (!container.getItem(slot).isEmpty()) {
                continue;
            }
            int transferable = Math.min(remainder.getCount(), remainder.getMaxStackSize());
            container.setItem(slot, remainder.copyWithCount(transferable));
            remainder.shrink(transferable);
        }
        container.setChanged();
        return remainder;
    }
}
