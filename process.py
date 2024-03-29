from pathlib import Path
import logging
from urllib.parse import urlparse
from PIL import Image
import time

from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OUTPUT_DIR = "screenshots"
SIZES = {"mobile": 400, "medium": 900, "wide": 1300}


class Website:
    def __init__(self, page, url):
        self.page = page
        self.url = url

        pieces = urlparse(url)
        self.hostname = pieces.hostname
        if pieces.path.endswith("html"):
            self.urlpath = pieces.path.strip("/")
        else:
            self.urlpath = pieces.path.strip("/") + "/index.html"
        self.urlpath = self.urlpath.strip("/")

    def load(self):
        """Load the web page"""
        logger.info(f"{self.url}: Loading")

        try:
            response = self.page.goto(self.url, timeout=30000)
        except:
            # Exit early if fails to load
            self.successful_request = False
            return

        if response and response.ok:
            self.successful_request = True
        else:
            self.successful_request = False
        time.sleep(1)
        self.page.evaluate(
            "window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });"
        )
        time.sleep(2)

    def get_all_meta_tags(self):
        self.meta = {}
        self.meta['og:title'] = self.get_meta("og:title")
        # self.meta['og:type'] = self.get_meta("og:type")
        self.meta['og:description'] = self.get_meta("og:description")
        self.meta['og:image'] = self.get_meta("og:image")
        # self.meta['twitter:card'] = self.get_meta("twitter:card", "name")

    def get_meta(self, property, property_type='property'):
        try:
            logger.info(f"Getting {property}")
            return self.page.query_selector(f"meta[{property_type}='{property}']").get_attribute('content')
        except:
            return None

    def screenshot(self):
        """Take a screenshot at each screen size"""
        for size in SIZES.keys():
            self.screenshot_one(size)

    def build_desc(self):
        title = self.page.title() or self.urlpath
        for character in ['|', '[', ']']:
            title = title.replace(character, "")
        page_link = f"[{title}]({self.url})"

        self.get_all_meta_tags()
        
        metas = '<br>'.join([f":x: {key}" for key, value in self.meta.items() if value is None])

        if metas:
            desc = f"|{page_link}<br>{metas}<br>[how to fix](tips/SOCIAL.md)|"
        else:
            desc = f"|{page_link}|"
        return desc


    def get_table_row(self):
        """Markdown display of screenshots for this web page"""
        desc = self.build_desc()
        if self.successful_request:
            images = [
                f"[![{size}]({self.shot_path(size, 'thumb')})]({self.shot_path(size)})"
                for size in SIZES.keys()
            ]
        else:
            images = [ f"request failed" for size in SIZES.keys() ]

        return desc + "|".join(images) + "|"

    def shot_path(self, size, version="full"):
        """Returns the file path for a given screenshot size and version"""
        basename = self.urlpath.replace("/", "_").replace(" ", "%20")
        filename = f"{basename}-{size}-{version}.jpg"
        return Path(OUTPUT_DIR).joinpath(self.hostname).joinpath(filename)

    def screenshot_one(self, size):
        """Create a screenshot at a given screen width"""
        width = SIZES[size]
        filepath = self.shot_path(size)
        self.page.set_viewport_size({"width": width, "height": 700})
        time.sleep(0.5)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"{self.url}: {width}px screenshot to {filepath}")

        self.page.screenshot(path=filepath, full_page=True, type='jpeg')

        thumb_path = self.shot_path(size, "thumb")
        logger.info(f"{self.url}: Creating thumbnail at {thumb_path}")
        with Image.open(filepath) as img:
            box = (0, 0, img.size[0], img.size[0])
            img.crop(box).resize((400, 400)).save(thumb_path)
    
    def run_checks(self):
        logger.info(f"{self.url}: Running automatic checks")
        self.issues = []
        tiny_text = self.page.evaluate("""
        () => [...document.querySelectorAll(".ai2html p")]
            .filter(d => window.getComputedStyle(d)['font-size'].indexOf("px") != -1)
            .filter(d => parseFloat(window.getComputedStyle(d)['font-size']) < 11)
            .map((d) => {
                return {
                    text: d.innerText,
                    size: window.getComputedStyle(d)['font-size']
                }
            })
        """)
        self.page.set_viewport_size({"width": SIZES['mobile'], "height": 700})
        has_sideways_scroll = self.page.evaluate("() => document.body.scrollWidth > window.innerWidth")
        missing_viewport_tag = self.page.evaluate("() => !document.querySelector('meta[name=viewport]')")
        overlapping_elements = []
        for width in SIZES.values():
            self.page.set_viewport_size({"width": width, "height": 700})
            new_overlaps = self.page.evaluate("""
                () => {
                    function overlaps(e1, e2) {
                        const buffer = 5;
                        const rect1 = e1.getBoundingClientRect();
                        const rect2 = e2.getBoundingClientRect();
                        if(rect1.width == 0 || rect2.width == 0) {
                            return false
                        }
                        return !(rect1.right - buffer < rect2.left || 
                            rect1.left + buffer > rect2.right || 
                            rect1.bottom - buffer < rect2.top || 
                            rect1.top + buffer > rect2.bottom)
                    }

                    const elements = [...document.querySelectorAll('.ai2html p')];
                    const overlappingElements = []
                    for(let i = 0; i < elements.length; i++) {
                        const e1 = elements[i];
                        for(let j = i+1; j < elements.length; j++) {
                            const e2 = elements[j];
                            if(overlaps(e1, e2) && e1.innerText.trim() !== '' && e2.innerText.trim() !== '') {
                                overlappingElements.push({
                                    text1: e1.innerText,
                                    text2: e2.innerText,
                                    width: window.innerWidth
                                })
                            }
                        }
                    }
                    return overlappingElements
                }
            """)
            overlapping_elements.extend(new_overlaps)

        missing_fonts = self.page.evaluate("""
            () => {
                function groupBy(objectArray, property) {
                    return objectArray.reduce((acc, obj) => {
                    const key = obj[property];
                    if (!acc[key]) {
                        acc[key] = [];
                    }
                    // Add object to list for given key's value
                    acc[key].push(obj);
                    return acc;
                    }, { });
                }
                
                const objects = [...document.querySelectorAll(".ai2html p")]
                    .filter(d => !(document.fonts.check("12px " + window.getComputedStyle(d)['font-family'])))
                    .map(d => {
                        return {
                            text: d.innerText,
                            font: window.getComputedStyle(d)['font-family']
                        }
                    })

                return groupBy(objects, 'font')
            }
        """)

        img_missing_alt_tags = self.page.query_selector_all('img:not([alt])')
        if img_missing_alt_tags:
            self.issues.append(f"* Image(s) need `alt` tags, [info here](https://abilitynet.org.uk/news-blogs/five-golden-rules-compliant-alt-text) and [tips here](https://twitter.com/FrankElavsky/status/1469023374529765385)")
            for img in img_missing_alt_tags:
                self.issues.append(f"    * Image `{img.get_attribute('src')}` missing `alt` tag")

        datawrapper_charts = self.page.query_selector_all(".dw-chart")
        for chart in datawrapper_charts:
            if not chart.query_selector_all(".sr-only"):
                self.issues.append("* Datawrapper chart missing description, fill out *Alternative description for screen readers* section on Annotate tab, [tips here](https://twitter.com/FrankElavsky/status/1469023374529765385)")

        if not self.successful_request:
            self.issues.append("* Could not access the page - if you moved it, let me know")

        if not self.page.title():
            self.issues.append("* Needs a title, add a `<title>` tag to the `<head>`")

        if not self.urlpath.endswith("index.html"):
            name = self.urlpath.split("/")[-1].replace(".html", "")
            self.issues.append(f"* Move `{self.urlpath}` into a folder called `{name}`, then rename the file `index.html`. That way the project can be found at **/{name}** instead of **/{name}.html**. [Read more about index.html here](https://www.thoughtco.com/index-html-page-3466505)")

        if 'project' in self.url:
            self.issues.append("* Simplify URL by removing `project`. For example, `dog-names` instead of `dog-names-project`.")

        if ' ' in self.url or '_' in self.url:
            self.issues.append("* Change URL to use `-` instead of spaces or underscores")

        if self.url != self.url.lower():
            self.issues.append("* Change URL to be all in lowercase")

        if missing_viewport_tag:
            self.issues.append('* Missing viewport meta tag in `<head>`, needed to tell browser it\'s responsive. Add `<meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">`')
        if has_sideways_scroll:
            self.issues.append(f"* Has sideways scrollbars in mobile version – check padding, margins, image widths. Also make sure any embeds are the responsive version. [How to view the mobile version](https://www.howtogeek.com/739812/how-to-view-mobile-websites-on-your-computer-in-chrome/)")

        if tiny_text:
            self.issues.append("* Minimum font size should be 12px, enlarge text in Illustrator")
            for text in tiny_text[:7]:
                if text['text'] != "":
                    self.issues.append(f"    * Text `{text['text']}` is too small at {text['size']}")
            if len(tiny_text) > 7:
                self.issues.append(f"    * *and {len(tiny_text) - 7} more*")

        if overlapping_elements:
            self.issues.append("* Overlapping elements in ai2html, check [the overflow video](https://www.youtube.com/watch?v=6vHsnjTp3_w) or make a smaller size")
            for overlap in overlapping_elements[:7]:
                self.issues.append(f"   * Text `{overlap['text1']}` overlaps with `{overlap['text2']}` at screen width {overlap['width']}")
            if len(overlapping_elements) > 7:
                self.issues.append(f"   * *and {len(overlapping_elements) - 7} more*")

        if missing_fonts:
            self.issues.append("* Missing font(s), you might need web fonts – [text explanation](https://gist.github.com/jsoma/631621e0807b26d49f5aef5260f79162), [video explanation](https://www.youtube.com/watch?v=HNhIeb_jEYM&list=PLewNEVDy7gq3MSrrO3eMEW8PhGMEVh2X2&index=3)")
            for key, values in missing_fonts.items():
                self.issues.append(f"    * `{key}` font not found, used in {len(values)} text objects. Example: _{', '.join([v['text'] for v in values[:3]])}_")

        github_link = self.page.query_selector("a[href*='github.com']")
        if not github_link:
            self.issues.append("* Add a link to the repository with your source code/data/analysis: [tutorial](https://jonathansoma.com/fancy-github/), [example](https://github.com/ilenapeng/stevens-creek) from [a story](https://ilenapeng.github.io/data-studio/stevens-creek/)")

websites = [w for w in Path("websites.txt").read_text().split("\n") if w != ""]

table_starter = """
|url|mobile|medium|wide|
|---|---|---|---|
"""

readme_md = """"""
issues_md = """"""
toc_md = """"""

with sync_playwright() as p:
    browser = p.chromium.launch(
        args=[
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
        ]
    )
    page = browser.new_page()

    prev_host = None
    for website in websites:
        site = Website(page, website)
        if site.hostname != prev_host:
            readme_md += issues_md
            readme_md += f"\n\n## {site.hostname}\n\n{table_starter}"
            toc_md += f"* [{site.hostname}](#{site.hostname.replace('.','')})\n"
            issues_md = f"\n\n### Automatic Checks\n\n"
            prev_host = site.hostname
        site.load()
        if site.successful_request:
            site.screenshot()
        site.run_checks()

        readme_md += site.get_table_row() + "\n"

        issues_md += f"**{site.url}**\n\n"
        if site.issues:
            issues_md += '\n'.join(site.issues) + '\n\n'
        else:
            issues_md += f"No issues found! 🎉\n\n"

    readme_md += issues_md

    readme_md = (
        "# Lede Program 2022 Personal Projects Page\n\n" +
        "Along with quick checks to make sure your pages are looking their best!\n\n" +
        toc_md +
        "\n\n" +
        readme_md
    )

    Path("README.md").write_text(readme_md)

    browser.close()
