import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import urllib.request
import zipfile
import shutil

def download_images(url, output_folder):
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    img_tags = soup.find_all('img')
    
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    for idx, img_tag in enumerate(img_tags):
        img_url = img_tag.get('src')
        
        # Convert relative URL to absolute URL
        img_url = urljoin(url, img_url)
        
        img_name = f"{idx + 1:03d}.jpg"
        img_path = os.path.join(output_folder, img_name)
        
        try:
            urllib.request.urlretrieve(img_url, img_path)
            print(f"Downloaded: {img_name}")
        except Exception as e:
            print(f"Error downloading {img_name}: {e}")

def create_cbz_and_cleanup(title, folder):
    cbz_filename = f"{title}.cbz"
    with zipfile.ZipFile(cbz_filename, 'w') as zipf:
        for root, _, files in os.walk(folder):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, folder)
                zipf.write(file_path, arcname)
    
    shutil.rmtree(folder)  # Delete the downloaded folder after creating the cbz

if __name__ == "__main__":
    with open("web.txt", "r") as file:
        urls = file.read().splitlines()
    
    for url in urls:
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        title = soup.title.string.strip()
        
        output_folder = "downloaded_images"
        
        download_images(url, output_folder)
        create_cbz_and_cleanup(title, output_folder)
        
        print(f"Download, cbz creation, and cleanup complete for: {title}")

