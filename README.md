# Epic7 Assist Bot (EAB)

[English](README.md) | [한국어](README.ko.md)

EAB is a Windows desktop tool that automates repetitive tasks in **Epic Seven**. It supports the STOVE PC client and Android emulators connected through ADB.

Features include Secret Shop refreshes and purchases, Penguin purchases, and Dimensional Exploration.

[Download the latest release](https://github.com/pelierze/EAB/releases/latest) · [Report an issue](https://github.com/pelierze/EAB/issues)

## Language support

Open the **Language** menu at the top of the app and select **English** or **한국어** (Korean). Your choice is saved across restarts and updates. This changes the app's interface; it does not change the game's language.

| Feature | English interface | Korean interface |
| --- | --- | --- |
| Secret Shop | Available | Available |
| Penguin purchases | Available | Available |
| Dimensional Exploration | Not yet available | Available |
| Event tab | Disabled | No events currently supported |

Secret Shop and Penguin purchases use the same recognition logic for Korean and English game screens. Dimensional Exploration does not currently support English game screens. Some runtime logs and diagnostic messages remain in Korean even when the app uses English.

## Download and run

1. Open the [latest release](https://github.com/pelierze/EAB/releases/latest).
2. Under **Assets**, download `EAB-v<version>.zip`, such as `EAB-v1.6.0.zip`. Use the release ZIP rather than GitHub's **Source code** downloads.
3. Extract the entire archive to a folder.
4. Run **EAB.exe** inside that folder. Keep the other files and the `_internal` folder alongside it; do not move the executable on its own.

The packaged release does not require a separate Python installation. Windows may request administrator permission when the app starts.

EAB was previously named **SecretShopBot-E7**. The included compatibility launcher keeps existing shortcuts working. When opened through an old shortcut, it creates an EAB shortcut in the same location and removes the old one only after the replacement succeeds. Running the old executable directly creates an EAB shortcut on the desktop. Running `EAB.exe` directly or using automatic updates does not create shortcuts.

## Connect the game

### STOVE PC client

1. Launch Epic Seven through STOVE and leave the game window open.
2. In EAB, set **Environment** to **STOVE PC Client**.
3. Click **Refresh Windows**, choose the game under **Epic Seven Window**, and click **Connect**.
4. Stop any running bot, then click **Resize to 1280×720** to match the expected game size. Use the game's normal windowed mode for this option.

Keep the game window open and **not minimized** while the bot runs. If input does not work, use **Restart as Admin** when that button is available.

STOVE captures are normalized to a 1280×720 reference size. Other window sizes may work, but differences in aspect ratio or UI layout can affect recognition.

### Android emulator (ADB)

1. Set the emulator's resolution to **1280×720** and DPI to **240**.
2. Enable **ADB debugging** in the emulator's settings and launch Epic Seven.
3. In EAB, set **Environment** to **Emulator (ADB)**.
4. Click **Scan Devices**, select the emulator under **Device**, and click **Connect**.

If the device does not appear, check that ADB debugging is enabled and that the connection port matches the emulator's settings. You can enter the **IP Address** and **Port** manually when needed.

For multiple emulators, connect a different device to each session.

## Using the features

Open the appropriate starting screen in the game before starting a bot. Begin with a small run count to check the setup. The **Logs** panel shows progress and reasons for stopping.

### Secret Shop

1. Open the Secret Shop in the game.
2. Select the **Secret Shop** tab in EAB.
3. Set **Refresh Count** or **Skystones to Use**. Enable **Buy Friendship Points** if you also want to purchase that item.
4. Click **Start**. Use **Pause**, **Resume**, or **Stop** as needed.

The bot looks for **Mystic Medals** and **Covenant Bookmarks**, purchases them, and refreshes the shop.

To avoid spending Skystones on refreshes, enable **Free Refresh Only**. Leave the game on the shop screen. This mode checks the shop at 15-minute intervals and continues until you stop it. Item purchases still consume the required in-game currency.

### Penguin purchases

1. Open **Forest of Souls → Growth Altar** in the game and leave the Penguin purchase list visible.
2. Select the **Penguins** tab in EAB.
3. Enter the number of **Purchase Cycles**.
4. Click **Start Penguin Run**. Use **Stop Penguin Run** to stop.

The bot selects the Stigma purchase control for the Penguin Nest, chooses the maximum quantity when needed, and confirms **50/50** before purchasing. Each cycle uses Stigma; the cycle count is the number of purchase repetitions.

### Dimensional Exploration

This feature is currently available through the **Korean interface** and targets Korean game screens. Switching the interface to English disables its tab.

1. In the game, select the desired difficulty and open the exploration starting screen. You can also start from the node map if a run is already in progress.
2. In EAB's exploration tab, select a hero for each class and set the rank-up priorities.
3. Enter the target number of completed runs and review the shop and unrecognized-event options.
4. Start exploration, or use its stop control to end the run.

The bot handles recruitment, node movement, battles, and results, then repeats until it reaches the target run count. It uses the difficulty already selected in the game.

Hero choices, rank-up priorities, and the fallback-hero option are saved automatically for each session. The last configuration is restored for the same Windows user, including after automatic updates or a manual update to a new folder.

Event choices are selected randomly from detected buttons after excluding forbidden, disabled, and previously canceled choices. The bot does not read the choice text, so it may select choices with unfavorable outcomes. If it cannot recognize a screen or confirm progress, it may stop; check the logs and the game screen.

### Events

No events are currently supported. In the Korean interface, this tab displays a notice only; it is disabled in the English interface.

## Updating

When an update is offered, review the release notes and choose **Update & Restart**. Select **Later** to postpone it. Running bots do not resume automatically after updating.

- **v1.5.15 and later:** automatic updates support the EAB package format.
- **v1.5.14 and earlier:** download the latest EAB ZIP and install it manually.

For a manual update, close the app, extract the latest ZIP to a **new folder**, and run `EAB.exe`. Keep the entire extracted folder together.

## Troubleshooting and issue reports

Check the connection and the current game screen first. For emulators, also check the resolution and DPI. Use **Image Test** to investigate Secret Shop recognition, and enable **Debug Mode (Detailed Logs)** when collecting additional Secret Shop diagnostics.

If a problem persists, [open an issue](https://github.com/pelierze/EAB/issues) with:

- The EAB version, interface language, and game language.
- Whether you use STOVE or an emulator; include the emulator name when applicable.
- The feature, steps to reproduce the issue, and expected versus actual behavior.
- A screenshot and the relevant logs or error-report folder.

### Automation error reports

When automation stops because of an error, EAB saves the available recent logs, last screenshot, and stop reason under **`logs/report`**. The log panel shows the report location. Normal completion and a manual stop do not create an error report. If a screenshot cannot be captured, the report contains the available logs and reason instead.

Secret Shop reports may also include before-and-after images for the last two scroll gestures in a **`scrolls`** subfolder. Some images may be missing if a capture failed or the bot stopped before the next capture. Attach the **entire report folder as a ZIP**, including `scrolls` when present.

### Startup and update errors

Paste this path into the Windows File Explorer address bar:

```text
%LOCALAPPDATA%\SecretShopBot-E7\logs
```

Check **`startup.log`** and **`updater.log`**. The folder retains the old application name for compatibility.

If Windows blocks the executable before it starts, no new startup log may be created. Include the error screen and relevant antivirus protection history in your report. Review screenshots and logs for personal information before attaching them.

## Contributing

Bug reports, feature requests, documentation improvements, and code contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for development and contribution instructions, currently written in Korean. You can submit [issues](https://github.com/pelierze/EAB/issues) in English.

## License and responsible use

The source code is licensed under the [GNU General Public License v3.0 (GPL-3.0-only)](LICENSE). When distributing modified versions or binaries, provide the corresponding source code as required by GPLv3. The software is provided without warranty. Third-party libraries and assets remain subject to their respective licenses and rights.

Check the game's terms of service before use. You are responsible for account penalties or loss of in-game currency resulting from automation.
