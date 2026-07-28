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
import net.minecraft.world.level.block.entity.ChestBlockEntity;
import net.neoforged.fml.ModList;
import net.neoforged.neoforge.gametest.GameTestHolder;
import net.neoforged.neoforge.gametest.PrefixGameTestTemplate;

import java.util.List;
import java.util.UUID;

@GameTestHolder("workers")
@PrefixGameTestTemplate(false)
public final class WorkersFinalGameTests {
    private static final UUID OWNER = UUID.fromString("00000000-0000-0000-0000-000000000001");

    private WorkersFinalGameTests() {
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
        StorageArea storage = newStorage(helper, new BlockPos(1, 1, 1), 1, 1);
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
        BlockPos chest = new BlockPos(1, 1, 1);
        helper.setBlock(chest, Blocks.CHEST);
        StorageArea storage = newStorage(helper, chest, 1, 1);
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
    public static void storageAreaSplitsSixtyPlusTen(GameTestHelper helper) {
        BlockPos chest = new BlockPos(1, 1, 1);
        helper.setBlock(chest, Blocks.CHEST);
        StorageArea storage = newStorage(helper, chest, 1, 1);
        storage.scanStorageBlocks();
        storage.setItem(0, new ItemStack(Items.WHEAT, 64));
        storage.setItem(1, new ItemStack(Items.WHEAT, 6));
        helper.assertValueEqual(storage.getItem(0).getCount(), 64, "First stack must be 64");
        helper.assertValueEqual(storage.getItem(1).getCount(), 6, "Remainder must be 6");
        ItemStack removed = storage.removeItem(1, 4);
        helper.assertValueEqual(removed.getCount(), 4, "Exactly four wheat must be removed");
        helper.assertValueEqual(storage.getItem(1).getCount(), 2, "Two wheat must remain");
        storage.setChanged();
        helper.succeed();
    }

    @GameTest(templateNamespace = "minecraft", template = "empty", timeoutTicks = 120)
    public static void storageAreaContinuesIntoSecondChest(GameTestHelper helper) {
        BlockPos first = new BlockPos(2, 1, 2);
        BlockPos second = new BlockPos(4, 1, 2);
        helper.setBlock(first, Blocks.CHEST);
        helper.setBlock(second, Blocks.CHEST);
        StorageArea storage = newStorage(helper, second, 3, 1);
        storage.scanStorageBlocks();
        helper.assertValueEqual(storage.getContainerSize(), 54,
                "Two separate chests must expose 54 slots");
        for (int slot = 0; slot < 27; slot++) {
            storage.setItem(slot, new ItemStack(Items.COBBLESTONE, 64));
        }
        storage.setItem(27, new ItemStack(Items.WHEAT, 6));
        helper.assertValueEqual(storage.getItem(27).getCount(), 6,
                "The second chest must receive the remainder");
        storage.setChanged();
        helper.succeed();
    }

    @GameTest(templateNamespace = "minecraft", template = "empty", timeoutTicks = 120)
    public static void storageAreaRescansAfterEntityReload(GameTestHelper helper) {
        BlockPos chest = new BlockPos(1, 1, 1);
        helper.setBlock(chest, Blocks.CHEST);
        ChestBlockEntity chestEntity = (ChestBlockEntity) helper.getBlockEntity(chest);
        chestEntity.setItem(0, new ItemStack(Items.WHEAT, 64));
        chestEntity.setItem(1, new ItemStack(Items.WHEAT, 6));
        chestEntity.setChanged();

        StorageArea storage = newStorage(helper, chest, 1, 1);
        storage.setStorageTypes(8);
        CompoundTag saved = storage.saveWithoutId(new CompoundTag());
        storage.discard();

        StorageArea restored = ModEntityTypes.STORAGEAREA.get().create(helper.getLevel());
        helper.assertTrue(restored != null, "Restored StorageArea failed to instantiate");
        restored.load(saved);
        helper.assertTrue(helper.getLevel().addFreshEntity(restored),
                "Restored StorageArea could not be added");
        restored.scanStorageBlocks();
        helper.assertValueEqual(restored.getContainerSize(), 27,
                "Restored StorageArea must rediscover the chest");
        helper.assertValueEqual(restored.getItem(0).getCount(), 64,
                "Persisted first stack must be visible");
        helper.assertValueEqual(restored.getItem(1).getCount(), 6,
                "Persisted remainder must be visible");
        helper.assertValueEqual(restored.getStorageMask(restored.getStorageTypes()), 8,
                "Restored permission mask must remain 8");
        helper.succeed();
    }

    private static StorageArea newStorage(GameTestHelper helper, BlockPos chestRelative,
                                          int width, int depth) {
        StorageArea storage = ModEntityTypes.STORAGEAREA.get().create(helper.getLevel());
        helper.assertTrue(storage != null, "StorageArea failed to instantiate");
        storage.setPlayerUUID(OWNER);
        storage.setPlayerName("gametest");
        storage.setWidthSize(width);
        storage.setHeightSize(0);
        storage.setDepthSize(depth);
        BlockPos chestAbsolute = helper.absolutePos(chestRelative);
        storage.setPos(chestAbsolute.getX() + 0.5D, chestAbsolute.getY() + 1.0D,
                chestAbsolute.getZ() + 0.5D);
        helper.assertTrue(helper.getLevel().addFreshEntity(storage),
                "StorageArea could not be added to the level");
        return storage;
    }
}
