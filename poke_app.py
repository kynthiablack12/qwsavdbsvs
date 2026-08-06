import subprocess, time
ADB = r"C:\adb\adb.exe"
# poke the app a few times after token expiry to force a refresh call
deadline = time.time() + 8 * 60
last = 0
while time.time() < deadline:
    now = int(time.time())
    if now >= 1785997490 + 10 and now - last > 20:
        last = now
        subprocess.run([ADB, "-s", "emulator-5554", "shell",
            "am start -n ru.tander.magnit/.presentation.MainActivity"], capture_output=True)
        print(now, "poked app")
    time.sleep(5)
print("done")
