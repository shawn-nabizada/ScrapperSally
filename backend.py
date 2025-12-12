import time
import os
import threading
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

class PortalBackend:
    BASE_URL = os.getenv("BASE_URL")

    def __init__(self, cookies_path):
        self.cookies_path = cookies_path
        self.playwright = None
        self.browser = None
        self.context = None
        self._thread_id = None

    def _get_context(self):
        # Check for thread mismatch and restart if necessary (Streamlit safety)
        if self.playwright and self._thread_id != threading.get_ident():
            print("Thread mismatch detected (Streamlit re-run). Restarting Playwright session...")
            self.close_session()

        if not self.playwright:
             self.playwright = sync_playwright().start()
             self._thread_id = threading.get_ident()
        
        if not self.browser:
             self.browser = self.playwright.chromium.launch(headless=False)
             
        if not self.context:
             self.context = self.browser.new_context()
             # Load cookies
             cookies = []
             try:
                 with open(self.cookies_path, 'r') as f:
                     for line in f:
                         if line.startswith('#') or not line.strip():
                             continue
                         parts = line.strip().split('\t')
                         if len(parts) >= 7:
                             try:
                                 cookie = {
                                     'domain': parts[0],
                                     'path': parts[2],
                                     'secure': parts[3].upper() == 'TRUE',
                                     'expires': float(parts[4]),
                                     'name': parts[5],
                                     'value': parts[6]
                                 }
                                 cookies.append(cookie)
                             except ValueError:
                                 continue
                 if cookies:
                     self.context.add_cookies(cookies)
             except Exception as e:
                 print(f"Failed to load cookies: {e}")
            
        return self.playwright, self.browser, self.context

    def close_session(self):
        if self.context:
            try: self.context.close()
            except: pass
            self.context = None
        if self.browser:
            try: self.browser.close()
            except: pass
            self.browser = None
        if self.playwright:
            try: self.playwright.stop()
            except: pass
            self.playwright = None
            self._thread_id = None

    def get_courses(self):
        playwright, browser, context = self._get_context()
        page = context.new_page()
        courses = []
        try:
            # Navigate to dashboard
            page.goto(f"{self.BASE_URL}/Web/MyWorkspaces/")
            
            # Wait for items to verify load
            try:
                page.wait_for_selector('li.item', timeout=10000)
            except:
                print("No courses found or dashboard load failed.")

            items = page.query_selector_all('li.item')
            for item in items:
                title_el = item.query_selector('.titleLabel')
                desc_el = item.query_selector('.descLabel')
                link_el = item.query_selector('a.catalogBtn')

                if title_el and link_el:
                    title = title_el.inner_text().strip()
                    block = desc_el.inner_text().strip() if desc_el else ""
                    href = link_el.get_attribute('href')

                    if href and not href.startswith('http'):
                        href = self.BASE_URL + href

                    courses.append({
                        'title': title,
                        'block': block,
                        'url': href
                    })
        finally:
            page.close()
            context.close()
            browser.close()
            playwright.stop()
        return courses

    def get_lectures(self, course_url):
        playwright, browser, context = self._get_context()
        page = context.new_page()
        lectures = []
        try:
            page.goto(course_url)
            
            # Step A: Wait for .instanceResource
            try:
                page.wait_for_selector('div.instanceResource', timeout=15000)
            except:
                print("No course instances found.")
            
            if page.query_selector('div.instanceResource'):
                # Step B: Find all containers
                containers = page.query_selector_all('div.instanceResource')

                # Step C: Loop through containers
                for container in containers:
                    # Extract Class Name
                    h2 = container.query_selector('h2.resource-title')
                    if not h2:
                        continue
                    class_name = h2.inner_text().strip()

                    # Loop through rows
                    rows = container.query_selector_all('tr.k-master-row')
                    for row in rows:
                        # Extract Recording Name
                        anchor = row.query_selector('a')
                        if not anchor:
                            continue
                            
                        recording_name = anchor.inner_text().strip()
                        full_name = f"{class_name} - {recording_name}"
                        
                        # Extract Selector Info
                        onclick_text = anchor.get_attribute('onclick')
                        
                        selector_strategy = {
                            'type': 'text_in_container',
                            'container_text': class_name,
                            'link_text': recording_name,
                            'onclick': onclick_text
                        }

                        lectures.append({
                            'name': full_name,
                            'course_url': course_url, # Needed for navigation
                            'selector_data': selector_strategy
                        })
                    
        finally:
            page.close()
            context.close()
            browser.close()
            playwright.stop()
        return lectures

    def get_video_stream(self, lecture_data):
        playwright, browser, context = self._get_context()
        
        trigger_page = context.new_page()
        found_urls = []
        
        try:
            course_url = lecture_data.get('course_url')
            if not course_url:
                print("No course URL in lecture data.")
                return []

            trigger_page.goto(course_url)
            trigger_page.wait_for_selector('div.instanceResource', timeout=15000)

            # The Trigger
            selector_data = lecture_data.get('selector_data', {})
            container_text = selector_data.get('container_text')
            link_text = selector_data.get('link_text')

            container = trigger_page.locator("div.instanceResource").filter(has_text=container_text)
            row = container.locator("tr.k-master-row").filter(has_text=link_text)
            button = row.locator("a") 

            # The Popup
            with context.expect_page() as new_page_info:
                button.click()
            
            video_page = new_page_info.value
            video_page.wait_for_load_state()

            # Handle Flutter
            try:
                print("Waiting for Flutter to initialize...")
                # Flutter apps render into a <flutter-view>
                video_page.wait_for_selector('flutter-view', timeout=30000)
                
                # Sniffing setup: Broad Spectrum (WebSockets + Response Inspection)
                def on_websocket(ws):
                    print(f">> WEBSOCKET: {ws.url}")

                video_page.on("websocket", on_websocket)

                def on_response(response):
                    nonlocal found_urls
                    try:
                        url = response.url
                        ct = response.headers.get("content-type", "").lower()
                        
                        # Filter noise
                        if any(x in ct for x in ["image", "css", "font", "javascript", "svg", "woff"]):
                            return

                        # 1. Verbose Logging
                        print(f">> TRAFFIC: [{ct}] {url}")

                        # 2. Keyword Search
                        if any(k in url.lower() for k in ["master", "manifest", "playlist", "chunklist"]):
                             print(f">> POTENTIAL MATCH: URL contains stream keyword: {url}")

                        # 3. Deep Inspection
                        if "json" in ct or "text/plain" in ct:
                            try:
                                body = response.text()
                                if ".m3u8" in body or ".mpd" in body:
                                    print(f"MATCH (Deep Inspection): Found stream key inside {ct} body!")
                                    if "#EXTM3U" in body:
                                         if url not in found_urls:
                                             found_urls.append(url)
                            except:
                                pass

                        # 4. Standard Inspection
                        target_types = [
                            "application/vnd.apple.mpegurl",
                            "application/x-mpegurl",
                            "application/dash+xml",
                            "video/mp4"
                        ]

                        if any(t in ct for t in target_types):
                            print(f"MATCH (MIME): Found stream via MIME: {ct}")
                        if any(t in ct for t in target_types):
                            print(f"MATCH (MIME): Found stream via MIME: {ct}")
                            if url not in found_urls:
                                found_urls.append(url)

                        if ".m3u8" in url or ".mpd" in url or ".mp4" in url:
                             print(f"MATCH (URL): Found stream via URL pattern.")
                             if url not in found_urls:
                                 found_urls.append(url)
                        
                    except Exception as e:
                        pass

                video_page.on("response", on_response)

                # Fix 2: Explicitly wake up accessibility tree via Keyboard
                print("Waking up Flutter accessibility tree via Keyboard...")
                try:
                    video_page.focus("flutter-view")
                    for _ in range(3):
                        video_page.keyboard.press("Tab")
                        time.sleep(0.5)
                except Exception as e:
                    print(f"Error sending keystrokes: {e}")

                print("Looking for playback button...")
                playback_button = None
                
                # Retry loop
                start_search = time.time()
                while time.time() - start_search < 10:
                    try:
                        btn = video_page.get_by_role("button", name="Playback the recording")
                        if btn.is_visible():
                            playback_button = btn
                            break
                    except:
                        pass
                    time.sleep(1)

                if playback_button:
                    print("Found button via accessibility tree. Clicking...")
                    playback_button.click(force=True)
                else:
                    print("Button not found in tree. Attempting fallback blind click...")
                    try:
                        video_page.locator("flutter-view").click(position={"x": 400, "y": 300}, force=True)
                    except Exception as e:
                        print(f"Blind click failed: {e}")

                # FULL SCRUB LOOP (0% to 100%)
                print("Waiting for stream URL and Scrubbing (Full JS Strategy)...")
                
                # 1. Robust Video Element Discovery (Main page + Frames)
                video_element = None
                try:
                    # Give it a moment to load
                    video_page.wait_for_timeout(5000)
                    
                    if video_page.locator("video").count() > 0:
                        video_element = video_page.locator("video").first
                        print("Found video on main page.")
                    else:
                        print("Video not on main page, checking frames...")
                        for frame in video_page.frames:
                            try:
                                if frame.locator("video").count() > 0:
                                    video_element = frame.locator("video").first
                                    print(f"Found video in frame: {frame.url}")
                                    break
                            except:
                                continue
                except Exception as e:
                    print(f"Error finding video element: {e}")

                if not video_element:
                    print("CRITICAL: Could not find <video> tag in page or frames. Scrubbing aborted.")
                else:
                    try:
                        # 2. Get Duration via Evaluate Handle
                        duration = video_element.evaluate("el => el.duration")
                        if not duration: duration = 600
                    except:
                        duration = 600
                    
                    print(f"Video duration: {duration}s. Starting FULL scrub loop...")
                    
                    # Iterate 10% to 90%
                    for i in range(1, 10): 
                        fraction = i / 10.0
                        target_time = duration * fraction
                        print(f"Scrubbing to {i*10}% ({target_time}s)...")
                        try:
                            # 3. Jump via Evaluate Handle
                            video_element.evaluate(f"el => el.currentTime = {target_time}")
                        except Exception as e:
                            print(f"Scrub jump failed: {e}")
                        
                        time.sleep(3.0) # Increased to 3s for reliability

                print(f"Scrub complete. Found {len(found_urls)} streams.")
            
            except Exception as e:
                print(f"Error on Flutter page: {e}")

        except Exception as e:
            print(f"Error in get_video_stream: {e}")
        
        # NO FINALLY BLOCK - Keep browser open!
        
        return found_urls # Returns list (ordered)
