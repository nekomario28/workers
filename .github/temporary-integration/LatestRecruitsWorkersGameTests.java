package com.talhanation.workers.gametest;

import com.talhanation.recruits.compat.workers.IVillagerWorker;
import com.talhanation.workers.entities.workarea.StorageArea;
import com.talhanation.workers.init.ModEntityTypes;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.Container;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.block.Blocks;
import net.neoforged.fml.ModList;
import net.neoforged.neoforge.gametest.GameTestHolder;
import net.neoforged.neoforge.gametest.PrefixGameTestTemplate;

import java.lang.reflect.Method;
import java.util.List;
import java.util.UUID;

@GameTestHolder("workers")
@PrefixGameTestTemplate(false)
public final class LatestRecruitsWorkersGameTests {
    private static final UUID OWNER = UUID.fromString("50000000-0000-0000-0000-000000000005");

    private LatestRecruitsWorkersGameTests() {
    }

    @GameTest(templateNamespace = "minecraft", template = "empty", timeoutTicks = 40)
    public static void exactModsLoad(GameTestHelper helper) {
        helper.assertTrue(ModList.get().isLoaded("recruits"), "Latest Recruits must load");
        helper.assertTrue(ModList.get().isLoaded("workers"), "Workers must load");
        helper.succeed();
    }

    @GameTest(templateNamespace = "minecraft", template = "empty", timeoutTicks = 100)
    public static void crossModEntityTypesInstantiate(GameTestHelper helper) {
        List<ResourceLocation> ids = List.of(
                ResourceLocation.fromNamespaceAndPath("recruits", "recruit"),
                ResourceLocation.fromNamespaceAndPath("workers", "farmer"),
                ResourceLocation.fromNamespaceAndPath("workers", "merchant"),
                ResourceLocation.fromNamespaceAndPath("workers", "courier"),
                ResourceLocation.fromNamespaceAndPath("workers", "storagearea")
        );
        for (ResourceLocation id : ids) {
            EntityType<?> type = BuiltInRegistries.ENTITY_TYPE.get(id);
            helper.assertTrue(type != EntityType.PIG || id.equals(BuiltInRegistries.ENTITY_TYPE.getKey(EntityType.PIG)),
                    "Missing entity type: " + id);
            Entity entity = type.create(helper.getLevel());
            helper.assertTrue(entity != null, "Could not instantiate entity type: " + id);
        }
        helper.succeed();
    }

    @GameTest(templateNamespace = "minecraft", template = "empty", timeoutTicks = 120)
    public static void storageCompositeContainerRemainsCorrect(GameTestHelper helper) {
        BlockPos chest = new BlockPos(1, 1, 1);
        helper.setBlock(chest, Blocks.CHEST);

        StorageArea storage = ModEntityTypes.STORAGEAREA.get().create(helper.getLevel());
        helper.assertTrue(storage != null, "StorageArea creation failed");
        storage.setPlayerUUID(OWNER);
        storage.setPlayerName("latest-integration");
        storage.setWidthSize(1);
        storage.setHeightSize(0);
        storage.setDepthSize(1);
        storage.setStorageTypes(8);
        BlockPos absolute = helper.absolutePos(chest);
        storage.setPos(absolute.getX() + 0.5D, absolute.getY() + 1.0D, absolute.getZ() + 0.5D);
        helper.assertTrue(helper.getLevel().addFreshEntity(storage), "StorageArea could not be added");
        storage.scanStorageBlocks();

        Container container = storage;
        helper.assertValueEqual(container.getContainerSize(), 27, "StorageArea must expose 27 slots");
        container.setItem(0, new ItemStack(Items.WHEAT, 64));
        container.setItem(1, new ItemStack(Items.WHEAT, 6));
        container.setChanged();
        helper.assertValueEqual(container.getItem(0).getCount(), 64, "First wheat stack must be 64");
        helper.assertValueEqual(container.getItem(1).getCount(), 6, "Remainder wheat stack must be 6");
        ItemStack removed = container.removeItem(1, 4);
        helper.assertValueEqual(removed.getCount(), 4, "Exactly four wheat must be removed");
        helper.assertValueEqual(container.getItem(1).getCount(), 2, "Two wheat must remain");
        helper.assertValueEqual(storage.getStorageMask(storage.getStorageTypes()), 8,
                "Farmer storage permission mask must remain 8");
        helper.succeed();
    }

    @GameTest(templateNamespace = "minecraft", template = "empty", timeoutTicks = 80)
    public static void workerCompatibilityApiIsDedicatedSafe(GameTestHelper helper) {
        for (Method method : IVillagerWorker.class.getDeclaredMethods()) {
            assertNotClientType(helper, method.getReturnType(), method.toString());
            for (Class<?> parameter : method.getParameterTypes()) {
                assertNotClientType(helper, parameter, method.toString());
            }
        }
        Entity courier = ModEntityTypes.COURIER.get().create(helper.getLevel());
        helper.assertTrue(courier instanceof IVillagerWorker,
                "Courier must implement Recruits IVillagerWorker compatibility API");
        helper.succeed();
    }

    private static void assertNotClientType(GameTestHelper helper, Class<?> type, String method) {
        String name = type.getName();
        helper.assertTrue(!name.startsWith("net.minecraft.client.") && !name.startsWith("com.mojang.blaze3d."),
                "Client-only type leaked through IVillagerWorker: " + method + " -> " + name);
    }
}
