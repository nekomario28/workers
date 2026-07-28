package com.talhanation.workers.client.finaltest;

import com.talhanation.workers.WorkersMain;
import net.minecraft.client.Minecraft;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.ModList;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.client.event.ClientTickEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

@EventBusSubscriber(modid = WorkersMain.MOD_ID, value = Dist.CLIENT, bus = EventBusSubscriber.Bus.GAME)
public final class LatestClientSmokeProbe {
    private static final Logger LOGGER = LoggerFactory.getLogger("LatestClientSmokeProbe");
    private static final Path PASS = Path.of("latest-client-smoke.pass");
    private static final Path FAIL = Path.of("latest-client-smoke.fail");
    private static int ticks;
    private static boolean completed;

    private LatestClientSmokeProbe() {
    }

    @SubscribeEvent
    public static void onClientTick(ClientTickEvent.Post event) {
        if (completed || ++ticks < 120) {
            return;
        }

        Minecraft minecraft = Minecraft.getInstance();
        if (minecraft.screen == null && ticks < 600) {
            return;
        }

        completed = true;
        try {
            require(ModList.get().isLoaded("recruits"), "Recruits is not loaded on the client");
            require(ModList.get().isLoaded("workers"), "Workers is not loaded on the client");
            require(minecraft.getWindow() != null, "Minecraft window was not created");
            require(minecraft.screen != null, "No client screen was reached");

            Class.forName("com.talhanation.recruits.client.events.ClientVillagerEvents");
            Class.forName("com.talhanation.workers.client.gui.WorkAreaScreenFactory");

            String screenClass = minecraft.screen.getClass().getName();
            Files.writeString(PASS,
                    "LATEST_CLIENT_SMOKE_OK\n"
                            + "recruits=1848e8ec33376f8a933945d4704b3e4c49920d8e\n"
                            + "workers=3859ceae9aa34464c3564597009608403a9fe8ea\n"
                            + "screen=" + screenClass + "\n"
                            + "clientVillagerEvents=true\n"
                            + "workAreaScreenFactory=true\n",
                    StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
            LOGGER.info("LATEST_CLIENT_SMOKE_OK screen={} recruits={} workers={} clientVillagerEvents={} workAreaScreenFactory={}",
                    screenClass,
                    "1848e8ec33376f8a933945d4704b3e4c49920d8e",
                    "3859ceae9aa34464c3564597009608403a9fe8ea",
                    true,
                    true);
            minecraft.stop();
        } catch (Throwable failure) {
            LOGGER.error("LATEST_CLIENT_SMOKE_FAILED", failure);
            try {
                Files.writeString(FAIL, failure.toString(),
                        StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
            } catch (Exception ignored) {
            }
            minecraft.stop();
            throw new IllegalStateException("Latest client smoke test failed", failure);
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
