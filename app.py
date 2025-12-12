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
            
            with st.spinner("Finding stream URL..."):
                stream_url = st.session_state.backend.get_video_stream(selected_recording)
            
            if stream_url:
                st.success(f"Stream found: {stream_url}")
                st.info("Starting download...")
                
                # Ensure Downloads directory exists
                os.makedirs("Downloads", exist_ok=True)
                
                # Run yt-dlp
                command = [
                    "uv", "run", "yt-dlp",
                    "-o", "Downloads/%(title)s.%(ext)s",
                    stream_url
                ]
                
                try:
                    with st.spinner("Downloading..."):
                        subprocess.run(command, check=True)
                    st.success("Download complete!")
                except subprocess.CalledProcessError as e:
                    st.error(f"Download failed: {e}")
            else:
                st.error("Could not find stream URL.")

else:
    st.info("Please load courses from the sidebar to begin.")
