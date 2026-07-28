package com.talhanation.workers.finaltest;

import com.talhanation.workers.WorkersMain;
import com.talhanation.workers.entities.workarea.StorageArea;
import com.talhanation.workers.init.ModEntityTypes;
import net.minecraft.core.BlockPos;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.entity.ChestBlockEntity;
import net.minecraft.world.phys.AABB;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.event.server.ServerStartedEvent;
import net.neoforged.neoforge.event.tick.ServerTickEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.List;
import java.util.UUID;

@EventBusSubscriber(modid = WorkersMain.MOD_ID, bus = EventBusSubscriber.Bus.GAME)
public final class FinalRestartProbe {
    private static final Logger LOGGER = LoggerFactory.getLogger("WorkersFinalRestartProbe");
    private static final Path PHASE = Path.of("workers-final-restart.phase");
    private static final Path PASS = Path.of("workers-final-restart.pass");
    private static final BlockPos CHEST_POS = new BlockPos(8, 100, 8);
    private static final UUID OWNER = UUID.fromString("00000000-0000-0000-0000-000000000001");
    private static int ticks;
    private static boolean completed;

    private FinalRestartProbe() {
    }

    @SubscribeEvent
    public static void onStarted(ServerStartedEvent event) {
        ticks = 0;
        completed = false;
        LOGGER.info("WORKERS_FINAL_RESTART_PROCESS_STARTED phaseExists={}", Files.exists(PHASE));
    }

    @SubscribeEvent
    public static void onTick(ServerTickEvent.Post event) {
        if (completed || ++ticks < 40) {
            return;
        }
        completed = true;
        MinecraftServer server = event.getServer();
        try {
            if (Files.exists(PHASE)) {
                verify(server);
            } else {
                write(server);
            }
        } catch (Throwable failure) {
            LOGGER.error("WORKERS_FINAL_RESTART_FAILED", failure);
            try {
                Files.writeString(Path.of("workers-final-restart.fail"), failure.toString(),
                        StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
            } catch (Exception ignored) {
            }
            throw new IllegalStateException("Workers final restart probe failed", failure);
        }
    }

    private static void write(MinecraftServer server) throws Exception {
        ServerLevel level = server.overworld();
        level.getChunkAt(CHEST_POS);
        level.setBlockAndUpdate(CHEST_POS.below(), Blocks.STONE.defaultBlockState());
        level.setBlockAndUpdate(CHEST_POS, Blocks.CHEST.defaultBlockState());
        ChestBlockEntity chest = requireChest(level);
        chest.setItem(0, new ItemStack(Items.WHEAT, 64));
        chest.setItem(1, new ItemStack(Items.WHEAT, 6));
        chest.setChanged();

        StorageArea storage = ModEntityTypes.STORAGEAREA.get().create(level);
        require(storage != null, "StorageArea creation returned null");
        storage.setPlayerUUID(OWNER);
        storage.setPlayerName("final-restart-probe");
        storage.setWidthSize(1);
        storage.setHeightSize(0);
        storage.setDepthSize(1);
        storage.setStorageTypes(8);
        storage.setPos(CHEST_POS.getX() + 0.5D, CHEST_POS.getY() + 1.0D, CHEST_POS.getZ() + 0.5D);
        require(level.addFreshEntity(storage), "StorageArea could not be added");
        storage.scanStorageBlocks();
        verifyBridge(storage);

        require(server.saveEverything(true, true, true), "saveEverything returned false");
        Files.writeString(PHASE, "write-ok\n", StandardOpenOption.CREATE,
                StandardOpenOption.TRUNCATE_EXISTING);
        LOGGER.info("WORKERS_FINAL_RESTART_WRITE_OK uuid={} storageTypes={} slots={} wheat0={} wheat1={}",
                storage.getUUID(), storage.getStorageMask(storage.getStorageTypes()),
                storage.getContainerSize(), storage.getItem(0).getCount(), storage.getItem(1).getCount());
        server.halt(false);
    }

    private static void verify(MinecraftServer server) throws Exception {
        ServerLevel level = server.overworld();
        level.getChunkAt(CHEST_POS);
        ChestBlockEntity chest = requireChest(level);
        require(chest.getItem(0).is(Items.WHEAT) && chest.getItem(0).getCount() == 64,
                "Chest slot 0 did not persist 64 wheat");
        require(chest.getItem(1).is(Items.WHEAT) && chest.getItem(1).getCount() == 6,
                "Chest slot 1 did not persist 6 wheat");

        List<StorageArea> storages = level.getEntitiesOfClass(StorageArea.class,
                new AABB(CHEST_POS).inflate(4.0D));
        require(storages.size() == 1, "Expected exactly one persisted StorageArea, found " + storages.size());
        StorageArea storage = storages.getFirst();
        require(OWNER.equals(storage.getPlayerUUID()), "Owner UUID did not persist");
        require("final-restart-probe".equals(storage.getPlayerName()), "Owner name did not persist");
        require(storage.getStorageMask(storage.getStorageTypes()) == 8,
                "Storage permission mask did not persist");
        storage.scanStorageBlocks();
        verifyBridge(storage);

        require(server.saveEverything(true, true, true), "verify saveEverything returned false");
        Files.writeString(PASS,
                "WORKERS_FINAL_RESTART_VERIFY_OK\nslots=27\nwheat0=64\nwheat1=6\nstorageTypes=8\n",
                StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
        LOGGER.info("WORKERS_FINAL_RESTART_VERIFY_OK uuid={} storageTypes={} slots={} wheat0={} wheat1={}",
                storage.getUUID(), storage.getStorageMask(storage.getStorageTypes()),
                storage.getContainerSize(), storage.getItem(0).getCount(), storage.getItem(1).getCount());
        server.halt(false);
    }

    private static ChestBlockEntity requireChest(ServerLevel level) {
        require(level.getBlockEntity(CHEST_POS) instanceof ChestBlockEntity,
                "Persisted block entity is not a chest");
        return (ChestBlockEntity) level.getBlockEntity(CHEST_POS);
    }

    private static void verifyBridge(StorageArea storage) {
        require(storage.getContainerSize() == 27, "StorageArea did not expose 27 chest slots");
        require(storage.getItem(0).is(Items.WHEAT) && storage.getItem(0).getCount() == 64,
                "StorageArea slot 0 is not 64 wheat");
        require(storage.getItem(1).is(Items.WHEAT) && storage.getItem(1).getCount() == 6,
                "StorageArea slot 1 is not 6 wheat");
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
