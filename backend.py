import time
import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

class PortalBackend:
    BASE_URL = os.getenv("BASE_URL")

    def __init__(self, cookies_path):
        self.cookies_path = cookies_path

    def _get_context(self):
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        
        # Load cookies
        cookies = []
        try:
            with open(self.cookies_path, 'r') as f:
                for line in f:
                    if line.startswith('#') or not line.strip():
                        continue
                    parts = line.strip().split('\t')
                    if len(parts) >= 7:
                        # Netscape format: domain, flag, path, secure, expiration, name, value
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
                context.add_cookies(cookies)
        except Exception as e:
            print(f"Failed to load cookies: {e}")
            
        return playwright, browser, context

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
        found_url = None
        
        try:
            course_url = lecture_data.get('course_url')
            if not course_url:
                print("No course URL in lecture data.")
                return None 

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
                
                # Sniffing setup
                def on_request(request):
                    nonlocal found_url
                    if not found_url and (request.url.endswith('.m3u8') or request.url.endswith('.mpd')):
                        found_url = request.url

                video_page.on("request", on_request)

                # Fix: Click 'Enable accessibility' if present to hydrate the semantic tree
                try:
                    semantics_btn = video_page.get_by_label("Enable accessibility")
                    if semantics_btn.is_visible(timeout=3000):
                        print("Clicking 'Enable accessibility' to wake up Flutter semantics...")
                        semantics_btn.click()
                        video_page.wait_for_timeout(2000) # Give it time to rebuild
                except:
                    pass

                print("Looking for playback button...")
                playback_button = None
                
                # Strategy 1: Role
                try:
                    btn = video_page.get_by_role("button", name="Playback the recording")
                    btn.wait_for(state="visible", timeout=3000)
                    playback_button = btn
                except:
                    pass
                
                # Strategy 2: Text
                if not playback_button:
                    try:
                        btn = video_page.get_by_text("Playback the recording")
                        btn.wait_for(state="visible", timeout=3000)
                        playback_button = btn
                    except:
                        pass
                
                if playback_button:
                    print("Clicking playback button...")
                    playback_button.click()
                    
                    # Wait loop for request
                    print("Waiting for stream URL...")
                    start_time = time.time()
                    while not found_url:
                        if time.time() - start_time > 30:
                            print("Timeout waiting for m3u8/mpd.")
                            break
                        video_page.wait_for_timeout(500)
                else:
                    print("Could not find 'Playback the recording' button.")
                    # Debug screenshot if we fail
                    try:
                        os.makedirs("debug_screenshots", exist_ok=True)
                        video_page.screenshot(path=f"debug_screenshots/flutter_fail_{int(time.time())}.png")
                        print("Screenshot saved to debug_screenshots/")
                    except:
                        pass

            except Exception as e:
                print(f"Error on Flutter page: {e}")
            finally:
                video_page.close()

        except Exception as e:
            print(f"Error in get_video_stream: {e}")
        finally:
            trigger_page.close()
            context.close()
            browser.close()
            playwright.stop()

        return found_url
