#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import shutil
import requests
import random
import argparse
import logging
import time
import urllib3
from bs4 import BeautifulSoup
from PIL import Image, ImageOps
import zipfile
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# 禁用HTTPS证书警告（可选）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 常量定义（移除序号相关前缀）
RETRY_TIMES = 3
TIMEOUT = 10
TEMP_DIR_PREFIX = "temp_"  # 临时目录仍用序号，避免冲突
WEB_TXT_PATH = "./web.txt"
ERROR_LOG_PATH = "error.log"
MAX_DOWNLOAD_WORKERS = 10
JPG_QUALITY = 95

# 模拟浏览器请求头
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36"
]

# 配置日志
logging.basicConfig(
    filename=ERROR_LOG_PATH,
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)


def check_dependencies():
    required = ['requests', 'bs4', 'PIL', 'tqdm']
    missing = []
    for lib in required:
        try:
            __import__(lib)
        except ImportError:
            missing.append(lib)
    if missing:
        print(f"错误：缺少依赖库：{', '.join(missing)}")
        print(f"安装命令：pip install {' '.join(missing)}")
        exit(1)


def parse_args():
    parser = argparse.ArgumentParser(description="网页图片下载打包工具（纯标题命名版）")
    parser.add_argument("--web", default=WEB_TXT_PATH, help=f"网址文件路径（默认：{WEB_TXT_PATH}）")
    parser.add_argument("--workers", type=int, default=MAX_DOWNLOAD_WORKERS,
                        help=f"下载并发数（默认：{MAX_DOWNLOAD_WORKERS}）")
    parser.add_argument("--retry", type=int, default=RETRY_TIMES, help=f"重试次数（默认：{RETRY_TIMES}）")
    parser.add_argument("--quality", type=int, default=JPG_QUALITY, help=f"JPG质量（1-100）")
    parser.add_argument("--skip-existing", action="store_true", help="跳过已存在的CBZ")
    return parser.parse_args()


def get_page_title(soup):
    """提取网页标题并处理特殊字符（确保符合文件系统命名规则）"""
    title_tag = soup.title
    if title_tag:
        title = title_tag.get_text(strip=True)
        # 移除文件系统不支持的字符（替换为下划线）
        invalid_chars = '/\\:*?"<>|'
        for c in invalid_chars:
            title = title.replace(c, '_')
        # 限制标题长度（避免过长文件名）
        return title[:100]  # 最长100字符
    return "unknown_title"  # 无标题时的默认名


def extract_image_urls(url):
    try:
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        response = requests.get(
            url,
            headers=headers,
            timeout=TIMEOUT,
            verify=False
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        img_urls = []

        # 提取<img>标签（支持懒加载）
        for img in soup.find_all('img'):
            for src_attr in ['src', 'data-src', 'data-original']:
                src = img.get(src_attr)
                if src and not src.startswith('data:'):  # 过滤base64图片
                    img_urls.append(urljoin(url, src))
                    break

        # 提取<source>标签图片
        for source in soup.find_all('source'):
            srcset = source.get('srcset')
            if srcset and not srcset.startswith('data:'):
                src = srcset.split(',')[-1].strip().split()[0]  # 取最高质量
                img_urls.append(urljoin(url, src))

        img_urls = list(dict.fromkeys(img_urls))  # 去重并保持顺序
        title = get_page_title(soup)
        return img_urls, title

    except Exception as e:
        logging.error(f"提取图片链接失败 ({url}): {str(e)}")
        print(f"提取图片链接失败: {str(e)}")
        return [], "unknown_title"


def download_image_with_retry(img_url, temp_dir, seq_str, retry_times):
    temp_path = os.path.join(temp_dir, f"temp_{seq_str}")
    headers = {"User-Agent": random.choice(USER_AGENTS)}

    for attempt in range(1, retry_times + 1):
        try:
            response = requests.get(
                img_url,
                headers=headers,
                timeout=TIMEOUT,
                stream=True,
                verify=False
            )
            response.raise_for_status()

            with open(temp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return temp_path

        except Exception as e:
            if attempt < retry_times:
                time.sleep(1)
            else:
                logging.error(f"[{seq_str}] 下载失败（{img_url}），重试{retry_times}次: {str(e)}")
                print(f"[{seq_str}] 下载失败（已重试{retry_times}次）")

    if os.path.exists(temp_path):
        os.remove(temp_path)
    return None


def convert_to_jpg(input_path, temp_dir, seq_str, quality):
    try:
        with Image.open(input_path) as img:
            # 处理透明背景（填充白色）
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                bg = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                bg.paste(img, mask=img.split()[-1])
                img = bg
            else:
                img = img.convert('RGB')

            jpg_path = os.path.join(temp_dir, f"{seq_str}.jpg")
            img.save(jpg_path, 'JPEG', quality=quality)

        os.remove(input_path)
        return jpg_path

    except Exception as e:
        logging.error(f"转换图片失败 ({input_path}): {str(e)}")
        print(f"转换图片 {seq_str} 失败: {str(e)}")
        if os.path.exists(input_path):
            os.remove(input_path)
        return None


def create_cbz(jpg_files, title):
    """生成CBZ文件，仅用网页标题作为文件名（无序号）"""
    if not jpg_files:
        return None

    safe_title = title.replace(' ', '_')  # 空格替换为下划线，避免命名问题
    zip_path = f"{safe_title}.zip"  # 中间ZIP文件名（纯标题）
    cbz_path = zip_path.replace('.zip', '.cbz')  # 最终CBZ文件名

    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zipf:
            # 按序号排序图片（确保顺序正确）
            for jpg in sorted(jpg_files, key=lambda x: os.path.basename(x)):
                zipf.write(jpg, os.path.basename(jpg))

        os.rename(zip_path, cbz_path)
        print(f"已生成CBZ：{cbz_path}")
        return cbz_path

    except Exception as e:
        logging.error(f"打包CBZ失败（{title}）: {str(e)}")
        print(f"打包CBZ失败: {str(e)}")
        if os.path.exists(zip_path):
            os.remove(zip_path)
        return None


def cleanup_temp_dir(temp_dir):
    try:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
    except Exception as e:
        logging.error(f"清理临时目录失败 ({temp_dir}): {str(e)}")
        print(f"警告：清理临时目录 {temp_dir} 失败: {str(e)}")


def main():
    check_dependencies()
    args = parse_args()

    if not os.path.exists(args.web):
        print(f"错误：未找到网址文件 {args.web}")
        logging.error(f"未找到网址文件 {args.web}")
        return

    with open(args.web, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip()]

    if not urls:
        print(f"警告：{args.web} 文件为空，无网址可处理")
        return

    # 统计变量
    total_urls = len(urls)
    successful_cbz = 0
    failed_urls = 0
    total_expected_images = 0
    successful_images = 0
    failed_images = 0

    for idx, url in enumerate(urls, start=1):
        # 临时目录仍用序号（避免不同网页标题相同导致冲突）
        temp_dir = f"{TEMP_DIR_PREFIX}{idx:03d}"
        print(f"\n===== 开始处理网址 {idx}/{total_urls}：{url} =====")

        # 提取网页标题（用于文件名）
        _, title = extract_image_urls(url)
        safe_title = title.replace(' ', '_')
        cbz_path = f"{safe_title}.cbz"  # 纯标题CBZ路径

        # 跳过已存在的CBZ
        if args.skip_existing and os.path.exists(cbz_path):
            print(f"CBZ文件已存在，跳过处理：{cbz_path}")
            continue

        os.makedirs(temp_dir, exist_ok=True)

        try:
            image_urls, page_title = extract_image_urls(url)
            total_expected_images += len(image_urls)
            print(f"发现 {len(image_urls)} 张图片，开始多线程下载...")

            if not image_urls:
                print("未找到有效图片，跳过该网址")
                cleanup_temp_dir(temp_dir)
                continue

            # 多线程下载
            downloaded_files = []
            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                future_dict = {}
                for seq, img_url in enumerate(image_urls, start=1):
                    seq_str = f"{seq:03d}"
                    future = executor.submit(
                        download_image_with_retry,
                        img_url, temp_dir, seq_str, args.retry
                    )
                    future_dict[future] = seq_str

                for future in tqdm(
                    as_completed(future_dict.keys()),
                    total=len(future_dict),
                    desc=f"下载进度 {idx}"
                ):
                    seq_str = future_dict[future]
                    result = future.result()
                    if result:
                        successful_images += 1
                        downloaded_files.append(result)
                    else:
                        failed_images += 1

            # 转换图片
            jpg_files = []
            if downloaded_files:
                print(f"转换 {len(downloaded_files)} 张图片为JPG...")
                for dl_file in downloaded_files:
                    seq_str = os.path.basename(dl_file).split('_')[-1]
                    jpg_path = convert_to_jpg(dl_file, temp_dir, seq_str, args.quality)
                    if jpg_path:
                        jpg_files.append(jpg_path)

            # 打包CBZ（仅用标题）
            if jpg_files:
                cbz_result = create_cbz(jpg_files, page_title)
                if cbz_result:
                    successful_cbz += 1
                    cleanup_temp_dir(temp_dir)
                    print(f"已清理临时目录：{temp_dir}")
                else:
                    failed_urls += 1
                    print(f"CBZ生成失败，保留临时文件：{temp_dir}")
            else:
                failed_urls += 1
                print("无有效图片可打包，保留临时目录")

        except Exception as e:
            failed_urls += 1
            logging.error(f"处理网址 {idx} ({url}) 异常: {str(e)}")
            print(f"处理失败: {str(e)}，继续下一个")
            cleanup_temp_dir(temp_dir)

    # 最终统计
    print("\n" + "="*50)
    print(f"处理完成！共 {total_urls} 个网址")
    print(f"成功生成 CBZ 文件：{successful_cbz} 个")
    print(f"处理失败的网址：{failed_urls} 个（详见 {ERROR_LOG_PATH}）")
    print(f"图片统计：总预期 {total_expected_images} 张，成功 {successful_images} 张，失败 {failed_images} 张")
    print("="*50)


if __name__ == "__main__":
    main()
