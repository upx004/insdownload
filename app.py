from flask import Flask, request, jsonify, send_file # 新增 send_file
from flask_cors import CORS
import instaloader
import re
import requests
from bs4 import BeautifulSoup
import io # 新增 io

app = Flask(__name__)
# 允许前端跨域请求
CORS(app)

# 初始化 instaloader (用于 Instagram)
L = instaloader.Instaloader()

def extract_ins_shortcode(url):
    match = re.search(r'/(?:p|reel)/([^/?#&]+)', url)
    if match:
        return match.group(1)
    return None

def parse_instagram(url):
    shortcode = extract_ins_shortcode(url)
    if not shortcode:
        raise ValueError('无效的 Instagram 链接')

    post = instaloader.Post.from_shortcode(L.context, shortcode)
    media_list = []
    
    if post.typename == 'GraphSidecar':
        for node in post.get_sidecar_nodes():
            if node.is_video:
                media_list.append({'type': 'video', 'url': node.video_url})
            else:
                media_list.append({'type': 'image', 'url': node.display_url})
    else:
        if post.is_video:
            media_list.append({'type': 'video', 'url': post.video_url})
        else:
            media_list.append({'type': 'image', 'url': post.url})
            
    return media_list

def parse_pinterest(url):
    # 伪装成浏览器访问，防止被 Pinterest 拦截
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    # requests 会自动处理 pin.it 的重定向跳转
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status() 
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # 从网页的 meta 标签中提取图片直链
    meta_image = soup.find('meta', property='og:image')
    if meta_image:
        img_url = meta_image['content']
        # Pinterest 的 meta 标签通常给的是 736x 宽度的压缩图，我们把它替换为 originals 获取最高画质原图
        img_url_high_res = img_url.replace('/736x/', '/originals/')
        return [{'type': 'image', 'url': img_url_high_res}]
        
    raise ValueError('未能在此 Pinterest 页面中找到图片。')


@app.route('/api/parse', methods=['POST'])
def parse_url():
    data = request.json
    url = data.get('url', '')
    
    if not url:
        return jsonify({'status': 'error', 'message': '链接不能为空'})

    try:
        # 智能路由：根据链接中的关键词决定使用哪个解析器
        if 'instagram.com' in url:
            media_list = parse_instagram(url)
        elif 'pinterest.com' in url or 'pin.it' in url:
            media_list = parse_pinterest(url)
        else:
            return jsonify({'status': 'error', 'message': '目前仅支持 Instagram 和 Pinterest (包含 pin.it) 的链接'})

        if not media_list:
            return jsonify({'status': 'error', 'message': '未找到任何媒体内容。'})

        return jsonify({
            'status': 'success',
            'media': media_list 
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/api/download', methods=['POST'])
def download_proxy():
    data = request.json
    url = data.get('url', '')
    
    if not url:
        return jsonify({'status': 'error', 'message': '链接不能为空'}), 400

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.pinterest.com/'
        }
        # 1. 让 Python 后端去请求这张外网图片
        response = requests.get(url, headers=headers, stream=True, timeout=10)
        response.raise_for_status()

        # 2. 将拿到的图片数据转换成文件流，直接塞给前端
        return send_file(
            io.BytesIO(response.content),
            mimetype=response.headers.get('Content-Type', 'image/jpeg')
        )
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)