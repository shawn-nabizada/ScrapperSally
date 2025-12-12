import streamlit as st
import subprocess
import os
from backend import PortalBackend

# Initialize backend
if 'backend' not in st.session_state:
    st.session_state.backend = PortalBackend('cookies.txt')

# Sidebar for Course Loading
with st.sidebar:
    if st.button("Load Courses"):
        with st.spinner("Loading courses..."):
            st.session_state.courses = st.session_state.backend.get_courses()
    
    st.divider()
    if st.button("Reset Browser Session"):
        st.session_state.backend.close_session()
        st.cache_resource.clear()
        st.rerun()

# Main Area
st.title("University Class Downloader")

if 'courses' in st.session_state and st.session_state.courses:
    courses = st.session_state.courses
    
    # 1. Filter by Block
    blocks = sorted(list(set(c['block'] for c in courses if c['block'])))
    selected_block = st.selectbox("Select Block", blocks)
    
    # 2. Filter by Course
    filtered_courses = [c for c in courses if c['block'] == selected_block]
    course_options = {f"{c['title']}": c for c in filtered_courses}
    selected_course_name = st.selectbox("Select Course", list(course_options.keys()))
    
    if st.button("Find Recordings"):
        with st.spinner("Finding recordings..."):
            selected_course = course_options[selected_course_name]
            st.session_state.recordings = st.session_state.backend.get_lectures(selected_course['url'])

    # 3. Select Recording
    if 'recordings' in st.session_state and st.session_state.recordings:
        recordings = st.session_state.recordings
        recording_options = {r['name']: r for r in recordings}
        selected_recording_name = st.selectbox("Select Recording", list(recording_options.keys()))
        
        if st.button("Download"):
            selected_recording = recording_options[selected_recording_name]
            
            with st.spinner("Finding stream URLs (Part 1 - Scrubbing)..."):
                stream_urls = st.session_state.backend.get_video_stream(selected_recording)
            
            if stream_urls:
                st.success(f"Found {len(stream_urls)} potential streams!")
                st.info("Starting robust downloads...")
                
                # Ensure Downloads directory exists
                os.makedirs("Downloads", exist_ok=True)
                
                # Iterate and Download
                for idx, stream_url in enumerate(stream_urls):
                    st.write(f"Downloading Stream #{idx+1}...")
                    
                    # Robust yt-dlp Command (The Impersonator Strategy)
                    command = [
                        "uv", "run", "yt-dlp",
                        "--force-ipv4",             # Fix IPv6 timeouts (OVH/AWS)
                        "--cookies", "cookies.txt", # Auth
                        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "--live-from-start",        # Get full history
                        "-x", "--audio-format", "mp3",
                        "-o", f"Downloads/%(title)s_part_{idx+1}.%(ext)s", # Prevent overwrite
                        stream_url
                    ]
                    
                    try:
                        with st.spinner(f"Downloading Part {idx+1}..."):
                            subprocess.run(command, check=True)
                        st.success(f"Part {idx+1} complete!")
                    except subprocess.CalledProcessError as e:
                        st.error(f"Download failed for Part {idx+1}: {e}")
            else:
                st.error("Could not find any stream URLs.")

else:
    st.info("Please load courses from the sidebar to begin.")
