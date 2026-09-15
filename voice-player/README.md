# Voice player (sender machine)

Plays audio files into a WhatsApp call as if they were spoken into a mic, so
the detector on the *other* laptop hears them as a caller. Copy this folder to
the sender machine; nothing here runs on the detector laptop.

## One-time setup (sender machine)

1. Install Python 3.10+ and [VB-Cable](https://vb-audio.com/Cable/), then reboot.
2. Start a WhatsApp call to the detector laptop. In the call's microphone menu
   (or WhatsApp Settings -> Audio), choose **CABLE Output (VB-Audio Virtual Cable)**.
3. Turn on clock sync on both machines (Settings -> Time & language -> Date & time
   -> *Sync now*), so the play log's timestamps line up with the detector's.

## Run

```powershell
.\run_player.ps1
```

The first run creates `.venv` and installs the requirements.

- **Send to** defaults to *CABLE Input*, which is where WhatsApp picks up the audio.
- **Also play on** plays the same clip on your headphones or speakers so you can hear what's being sent.
- **Add files...** accepts WAV, MP3, FLAC and OGG. Mark each clip `fake` / `real` before you play it.
- **Play selected** / **Play all** play the clips in list order, with the pause you set between them.

Each clip is appended to `playlog.csv`: UTC start/end, file, label, clip length,
seconds actually played, and whether it finished or was stopped.

## Things that affect the detector

- The detector ignores utterances under 3 s and pads 3-4 s ones. Use clips with
  at least 4 s of continuous speech so they are actually scored.
- Anything else the sender machine plays through CABLE Input is sent too.
  Leave CABLE Input as a playback target only; never set it as the Windows default output.
- On the detector laptop, capture is a loopback of the *whole* output device,
  not just WhatsApp. Notification sounds or a video playing there get scored as
  the caller, so keep that machine quiet during a test.

