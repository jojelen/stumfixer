#!/usr/bin/env python3
import time
import subprocess
import os
import sys
import atexit
import signal

PIDFILE = "/tmp/stumfixer.pid"
LOGFILE = "/tmp/stumfixer.log"
MAXLOGSIZE = 1000000


def daemonize(pidfile, *, stdin="/dev/null", stdout="/dev/null", stderr="/dev/null"):
    """
    Creates a daemon.
    """
    if os.path.exists(pidfile):
        exit(1)

    # First fork (detaches from parent).
    try:
        if os.fork() > 0:
            raise SystemExit(0)
    except OSError as e:
        raise RuntimeError("fork #1 failed.")

    os.chdir("/")
    os.umask(0)
    os.setsid()

    # Second fork (relinquish session leadership).
    try:
        if os.fork() > 0:
            raise SystemExit(0)
    except OSError as e:
        raise RuntimeError("fork #2 failed.")

    # Flush I/O buffers.
    sys.stdout.flush()
    sys.stderr.flush()

    # Replace file descriptors for stdin, stdout, and stderr.
    with open(stdin, "rb", 0) as f:
        os.dup2(f.fileno(), sys.stdin.fileno())
    with open(stdout, "ab", 0) as f:
        os.dup2(f.fileno(), sys.stdout.fileno())
    with open(stderr, "ab", 0) as f:
        os.dup2(f.fileno(), sys.stderr.fileno())

    # Write the PID file; which will be removed on exit.
    with open(pidfile, "w") as f:
        print(os.getpid(), file=f)
    atexit.register(lambda: os.remove(pidfile))

    # Signal handler for termination.
    def sigterm_handler(signo, frame):
        sys.stdout.write("{}: Quitting daemon\n".format(time.ctime()))
        raise SystemExit(1)

    signal.signal(signal.SIGTERM, sigterm_handler)


def switch_audio_to(active, name):
    """
    Sets audio card profile.
    """
    if active == name:
        return

    sys.stdout.write("{}: Setting card profile to {}\n".format(time.ctime(), name))
    try:
        proc = subprocess.Popen(
            ["pacmd", "set-card-profile", "0", name], stdout=subprocess.PIPE
        )
    except subprocess.CalledProcessError as e:
        raise SystemError("Could not run pacmd list-cards ({})".format(e.returncode))


def get_audio_info():
    """
    Returns the current active card profile and the last product; which
    is the one for hdmi (if it is available).
    """
    try:
        proc = subprocess.Popen(["pacmd", "list-cards"], stdout=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        raise SystemError("Could not run pacmd list-cards ({})".format(e.returncode))

    product = None
    active_profile = None

    for line in iter(proc.stdout.readline, ""):
        if line == b"":
            break

        line = line.decode("utf-8").strip()
        if line.startswith("active profile"):
            active_profile = line[17:-1]
        # TODO: Should perhaps return a list of all products.
        elif line.startswith("device.product.name"):
            product = line[23:-1]

    if active_profile is None:
        raise SystemError("Active profile is none")

    return active_profile, product


def check_log_file_size():
    size = os.path.getsize(LOGFILE)
    if size > MAXLOGSIZE:
        with open(LOGFILE, "a") as f:
            f.truncate(0)
        sys.stdout.write("{}: Cleaning up log file!\n".format(time.ctime()))


def main():
    sys.stdout.write(
        "{}: Stumfixer daemon started with pid={}\n".format(time.ctime(), os.getpid())
    )
    while True:
        active_profile, product = get_audio_info()

        if product.startswith("DELL"):
            switch_audio_to(active_profile, "output:analog-stereo+input:analog-stereo")
        elif product.startswith("BenQ"):
            switch_audio_to(active_profile, "output:hdmi-stereo")
        else:
            switch_audio_to(active_profile, "output:analog-stereo+input:analog-stereo")

        check_log_file_size()

        time.sleep(5)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: {} [start|stop]".format(sys.argv[0]), file=sys.stderr)
        raise SystemExit(1)

    if sys.argv[1] == "start":
        try:
            daemonize(PIDFILE, stdout=LOGFILE, stderr=LOGFILE)
        except RuntimeError as e:
            print(e, file=sys.stderr)
            raise SystemExit(1)

        main()

    elif sys.argv[1] == "stop":
        if os.path.exists(PIDFILE):
            with open(PIDFILE) as f:
                os.kill(int(f.read()), signal.SIGTERM)
        else:
            print("Not running", file=sys.stderr)
            raise SystemExit(1)

    else:
        print("Unknown command {!r}".format(sys.argv[1]), file=sys.stderr)
        raise SystemExit(1)
