# ptest/utils.py
import os
import sys
import logging
from pathlib import Path
from datetime import datetime
import json

def get_colored_text(text, color_code) -> str:
    """获取带颜色的文本"""
    return f"\033[{color_code}m{text}\033[0m"

def print_colored(text, color_code) -> None:
    """打印带颜色的文本"""
    print(get_colored_text(text, color_code))

def setup_logging(log_dir, level=logging.INFO) -> logging.Logger:
    """设置日志系统"""
    logger = logging.getLogger('ptest')
    logger.setLevel(level)
    
    # 清除现有处理器
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # 文件处理器
    if log_dir and Path(log_dir).exists():
        log_file = log_dir / f"ptest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger

def execute_command(cmd, timeout=30, cwd=None):
    """执行系统命令"""
    import subprocess
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd
        )
        if result.returncode == 0:
            return True, result.stdout
        else:
            return False, result.stderr
    except subprocess.TimeoutExpired:
        return False, f"Command timed out after {timeout}s"
    except Exception as e:
        return False, str(e)


