#!/usr/bin/env python3
"""Minimal crash program for demonstrating native crash capture.

This script simulates a real product process crash by calling os.abort().
Replace this with your actual product binary or test runner.
"""
import os
import sys

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "abort"

    if mode == "normal":
        print("process completed successfully")
        raise SystemExit(0)
    elif mode == "abort":
        print("process about to abort")
        os.abort()
    elif mode == "signal":
        import signal
        print("process about to receive SIGTERM")
        os.kill(os.getpid(), signal.SIGTERM)
    elif mode == "exit_nonzero":
        print("process exiting with code 1")
        raise SystemExit(1)
    else:
        print(f"unknown mode: {mode}")
        raise SystemExit(2)
