import subprocess
import time,datetime
import config

def adb(cmd):
    serial = config.DEVICE_ADDR
    prefix = f"adb -s {serial}" if serial else "adb"
    full_cmd = f"{prefix} {cmd}"
    try:
        res = subprocess.run(full_cmd, shell=True, capture_output=True, timeout=6)
        out = res.stdout.decode("gbk", errors="ignore")
        err = res.stderr.decode("gbk", errors="ignore")
        return out, err
    except:
        return "", ""


# -------------------- 主流程 ----------------------
def main():
        for i in range(1000):
            now = datetime.datetime.now()
            time_str = now.strftime("%H时%M分%S秒")
            print(f"\n🚨 开始第{i + 1}次测试，时间是{time_str}\n")
            adb("shell input keyevent 23 ")
            time.sleep(5)
            adb("shell  input keyevent 4")
            time.sleep(2)


if __name__ == "__main__":
    main()