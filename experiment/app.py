from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import requests
import json

app = Flask(__name__)
CORS(app)

# TikTok Video Scraper using public API
def get_tiktok_video_url(video_id):
    """
    Get direct video URL from TikTok video ID
    Using TikTok scraper API (you can use various services)
    """
    try:
        # Option 1: Using a TikTok scraper API (example with tikwm.com API)
        url = f"https://www.tikwm.com/api/?url=https://www.tiktok.com/@user/video/{video_id}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers)
        data = response.json()
        
        if data.get('code') == 0:
            video_url = data['data']['play']
            thumbnail = data['data']['cover']
            title = data['data']['title']
            author = data['data']['author']['nickname']
            
            return {
                'success': True,
                'video_url': video_url,
                'thumbnail': thumbnail,
                'title': title,
                'author': author
            }
        else:
            return {'success': False, 'error': 'Video not found'}
            
    except Exception as e:
        return {'success': False, 'error': str(e)}

# Sample trending videos (replace with real trending API)
TRENDING_VIDEOS = [
    '7565542482683907350',  # Your video
    '7450123456789012345',  # Add more trending video IDs
    '7460123456789012345',
]

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/video/<video_id>')
def get_video(video_id):
    """Get single video details"""
    result = get_tiktok_video_url(video_id)
    return jsonify(result)

@app.route('/api/trending')
def get_trending():
    """Get trending videos"""
    videos = []
    for video_id in TRENDING_VIDEOS:
        video_data = get_tiktok_video_url(video_id)
        if video_data.get('success'):
            videos.append({
                'id': video_id,
                'video_url': video_data['video_url'],
                'thumbnail': video_data['thumbnail'],
                'title': video_data['title'],
                'author': video_data['author']
            })
    
    return jsonify({'videos': videos})

@app.route('/api/proxy-video')
def proxy_video():
    """Proxy video to avoid CORS issues"""
    from flask import request, Response
    video_url = request.args.get('url')
    
    if not video_url:
        return jsonify({'error': 'No URL provided'}), 400
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.tiktok.com/'
        }
        
        response = requests.get(video_url, headers=headers, stream=True)
        
        return Response(
            response.iter_content(chunk_size=8192),
            content_type=response.headers.get('content-type'),
            headers={
                'Access-Control-Allow-Origin': '*',
                'Cache-Control': 'public, max-age=3600'
            }
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("🚀 TikTok Trending Videos Server")
    print("📺 Open: http://localhost:5000")
    print("📡 API: http://localhost:5000/api/trending")
    app.run(debug=True, port=5000)

