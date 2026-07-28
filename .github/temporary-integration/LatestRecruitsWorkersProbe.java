package com.talhanation.workers.finaltest;

import com.talhanation.recruits.compat.workers.IVillagerWorker;
import com.talhanation.workers.WorkersMain;
import com.talhanation.workers.init.ModEntityTypes;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.ModList;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.event.server.ServerStartedEvent;
import net.neoforged.neoforge.event.tick.ServerTickEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.List;

@EventBusSubscriber(modid = WorkersMain.MOD_ID, bus = EventBusSubscriber.Bus.GAME)
public final class LatestRecruitsWorkersProbe {
    private static final Logger LOGGER = LoggerFactory.getLogger("LatestRecruitsWorkersProbe");
    private static final Path PASS = Path.of("latest-recruits-workers.pass");
    private static final Path FAIL = Path.of("latest-recruits-workers.fail");
    private static int ticks;
    private static boolean completed;

    private LatestRecruitsWorkersProbe() {
    }

    @SubscribeEvent
    public static void onStarted(ServerStartedEvent event) {
        ticks = 0;
        completed = false;
        LOGGER.info("LATEST_RECRUITS_WORKERS_SERVER_STARTED");
    }

    @SubscribeEvent
    public static void onTick(ServerTickEvent.Post event) {
        if (completed || ++ticks < 80) {
            return;
        }
        completed = true;
        MinecraftServer server = event.getServer();
        try {
            require(ModList.get().isLoaded("recruits"), "Recruits is not loaded");
            require(ModList.get().isLoaded("workers"), "Workers is not loaded");

            List<ResourceLocation> ids = List.of(
                    ResourceLocation.fromNamespaceAndPath("recruits", "recruit"),
                    ResourceLocation.fromNamespaceAndPath("workers", "farmer"),
                    ResourceLocation.fromNamespaceAndPath("workers", "merchant"),
                    ResourceLocation.fromNamespaceAndPath("workers", "courier"),
                    ResourceLocation.fromNamespaceAndPath("workers", "storagearea")
            );
            for (ResourceLocation id : ids) {
                EntityType<?> type = BuiltInRegistries.ENTITY_TYPE.get(id);
                require(type != EntityType.PIG || id.equals(BuiltInRegistries.ENTITY_TYPE.getKey(EntityType.PIG)),
                        "Missing entity type: " + id);
                Entity entity = type.create(server.overworld());
                require(entity != null, "Entity creation failed: " + id);
            }

            Entity courier = ModEntityTypes.COURIER.get().create(server.overworld());
            require(courier instanceof IVillagerWorker,
                    "Courier does not implement IVillagerWorker");

            Files.writeString(PASS,
                    "LATEST_RECRUITS_WORKERS_INTEGRATION_OK\n"
                            + "recruits=1848e8ec33376f8a933945d4704b3e4c49920d8e\n"
                            + "workers=3859ceae9aa34464c3564597009608403a9fe8ea\n"
                            + "entities=5\n"
                            + "courierWorkerApi=true\n",
                    StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
            LOGGER.info("LATEST_RECRUITS_WORKERS_INTEGRATION_OK recruits={} workers={} entities={} courierWorkerApi={}",
                    "1848e8ec33376f8a933945d4704b3e4c49920d8e",
                    "3859ceae9aa34464c3564597009608403a9fe8ea", 5, true);
            server.halt(false);
        } catch (Throwable failure) {
            LOGGER.error("LATEST_RECRUITS_WORKERS_INTEGRATION_FAILED", failure);
            try {
                Files.writeString(FAIL, failure.toString(), StandardOpenOption.CREATE,
                        StandardOpenOption.TRUNCATE_EXISTING);
            } catch (Exception ignored) {
            }
            throw new IllegalStateException("Latest Recruits/Workers integration failed", failure);
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
