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
        StorageArea storage = ModEntityTypes.STORAGEAREA.get().create(helper.getLevel());
        helper.assertTrue(storage != null, "StorageArea failed to instantiate");
        storage.setPlayerUUID(UUID.fromString("00000000-0000-0000-0000-000000000001"));
        storage.setPlayerName("gametest");
        storage.setWidthSize(1);
        storage.setHeightSize(0);
        storage.setDepthSize(1);
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
        StorageArea storage = ModEntityTypes.STORAGEAREA.get().create(helper.getLevel());
        helper.assertTrue(storage != null, "StorageArea failed to instantiate");
        storage.setPlayerUUID(UUID.fromString("00000000-0000-0000-0000-000000000001"));
        storage.setPlayerName("gametest");
        storage.setWidthSize(1);
        storage.setHeightSize(0);
        storage.setDepthSize(1);
        BlockPos chestAbsolute = helper.absolutePos(chestRelative);
        storage.setPos(chestAbsolute.getX() + 0.5D, chestAbsolute.getY() + 1.0D,
                chestAbsolute.getZ() + 0.5D);
        helper.assertTrue(helper.getLevel().addFreshEntity(storage),
                "StorageArea could not be added to the level");
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
}
