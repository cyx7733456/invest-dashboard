#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看板每日自动更新（launchd 调用）：
每日重建 dashboard_v1 → 有变更则 commit → 走 7890 代理 push 到 GitHub Pages。
入口解释器必须是已授权 python3.13（launchd TCC 规则，禁止 /bin/bash 起手）。
日志：~/Library/Logs/wb/dashboard_daily.log（禁写 Desktop，launchd 规范）。
"""
import subprocess, os, sys, datetime

DASH = "/Users/apple/Desktop/Investment/公共/看板设计/dashboard_v1"
PY = "/Users/apple/.workbuddy/binaries/python/versions/3.13.12/bin/python3"
PROXY = ["-c", "http.proxy=http://127.0.0.1:7890"]
LOG = os.path.expanduser("~/Library/Logs/wb/dashboard_daily.log")


def log(msg):
    line = "[{}] {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def run(args, timeout=600):
    return subprocess.run(args, cwd=DASH, capture_output=True, text=True, timeout=timeout)


def main():
    today = datetime.date.today().isoformat()

    # 1. 重建
    r = run([PY, "_build.py"])
    tail = (r.stdout or "").strip()[-200:]
    log("build exit={} {}".format(r.returncode, tail))
    if r.returncode != 0:
        log("BUILD FAIL stderr: {}".format((r.stderr or "")[-500:]))
        sys.exit(1)

    # 2. 有无变更
    r = run(["git", "status", "--porcelain"])
    dirty = (r.stdout or "").strip()
    if not dirty:
        log("no changes, skip commit/push")
        return
    log("dirty files:\n{}".format(dirty[:800]))

    # 3. commit
    run(["git", "add", "-A"])
    r = run(["git", "commit", "-m", "dashboard daily auto update {}".format(today)])
    log("commit exit={} {}".format(r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()[-200:]))
    if r.returncode != 0:
        log("COMMIT FAIL: {}".format((r.stderr or "")[-300:]))
        sys.exit(2)

    # 4. push（代理）；被拒则 pull --rebase 后重试一次
    r = run(["git"] + PROXY + ["push"])
    log("push exit={} {}".format(r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()[-300:]))
    if r.returncode != 0:
        r2 = run(["git"] + PROXY + ["pull", "--rebase", "origin", "main"])
        log("pull-rebase exit={} {}".format(r2.returncode, ((r2.stdout or "") + (r2.stderr or "")).strip()[-300:]))
        if r2.returncode == 0:
            r3 = run(["git"] + PROXY + ["push"])
            log("push-retry exit={} {}".format(r3.returncode, ((r3.stdout or "") + (r3.stderr or "")).strip()[-300:]))
            sys.exit(0 if r3.returncode == 0 else 4)
        sys.exit(5)
    log("done")


main()
