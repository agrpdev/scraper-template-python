import time
from dotenv import load_dotenv
import asyncio
import os
from ScraperBase import BaseScraper
from playwright.async_api import async_playwright, Page
import sys
sys.path.append("..")


load_dotenv()

API_KEY = os.getenv('API_KEY')


class ArchiwebScraper(BaseScraper):
    async def process_crawl_item(self, work_item):
        async with async_playwright() as p:
            print('Crawling')
            # You can set headless=False to see the browser in action
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()

            try:
                for section in work_item['task']['sections']:
                    if section == 'zpravy':
                        await self.crawl_news(page)
                    elif section == 'architekti':
                        await self.crawl_architects(page)
            except Exception as error:
                print('Error during scraping:', error)
                await self.work_item_failed(work_item, error)
            finally:
                await self.work_item_completed(work_item)
                await browser.close()

    async def crawl_news(self, page: Page):
        custom_settings = self.details['customSettings']
        seen_hrefs = set()

        while True:
            await page.goto(custom_settings['crawlSections']['zpravy'])
            await page.click('.load_more')
            await page.wait_for_load_state('networkidle')

            links = await page.eval_on_selector_all('.row.newsList a[href]', '(links) => links.map(link => ({href: link.getAttribute("href"), date: link.querySelector("span.date")?.textContent?.trim() ?? "", title: link.querySelector("span.title")?.textContent?.trim() ?? "", commentCount: parseInt(link.querySelector("span.discuss")?.textContent?.trim() ?? "0")}))')

            new_links = [link for link in links if link['href']
                         and link['href'] not in seen_hrefs]

            metadata_list = [{
                'url': custom_settings['baseDomain'] + link['href'],
                'date': link['date'],
                'title': link['title'],
                'commentCount': link['commentCount'],
                'sections': 'zpravy'
            } for link in new_links]

            seen_hrefs.update(link['href'] for link in new_links)

            await self.send_scrape_targets(metadata_list)

    async def crawl_architects(self, page: Page):
        # Crawl architekti logic (similar to crawl_news)...
        pass

    async def process_scrape_item(self, work_item):
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()

            try:
                if work_item['task']['sections'] == 'zpravy':
                    await self.scrape_news(work_item, page)
                elif work_item['task']['sections'] == 'architekti':
                    await self.scrape_architects(work_item, page)
                else:
                    raise ValueError('Unknown content type')
            except Exception as error:
                print('Error during scraping:', error)
                await self.work_item_failed(work_item, error)
            finally:
                await self.work_item_completed(work_item)
                await browser.close()

    async def scrape_news(self, work_item, page: Page):
        await page.goto(work_item['task']['url'])

        title = await page.eval_on_selector('div.medium-12.columns.bottom > h1[itemprop="name"]', 'el => el.textContent')
        content = await page.eval_on_selector('section.sec_text2 > div[itemprop="description"]', 'el => el.textContent')
        article_info = await page.eval_on_selector('div.details', 'el => el.textContent')
        article_info_split = article_info.strip().split() if article_info else []
        datetime = article_info_split[-2:] if article_info_split and article_info_split[0] != 'Pořadatel' else None

        await self.send_scrape_records([{
            'id': work_item['task']['url'],
            'metadata': {
                'title': title,
                'content': content,
                'datetime': ' '.join(datetime) if datetime else None,
                'commentCount': work_item['task']['commentCount'],
                'linkTitle': work_item['task']['title'],
                'linkDate': work_item['task']['date'],
            },
            'createdOn': time.time(),
            'files': []
        }])

    async def scrape_architects(self, work_item, page: Page):
        # Scrape architekti logic (similar to scrape_news)...
        pass

# Run the scraper instance


async def run_instance():
    if not API_KEY:
        print('API key is required')
        return

    scraper_instance = ArchiwebScraper(custom_id='archiweb', api_key=API_KEY)
    configured = await scraper_instance.init()

    if not configured:
        print('Failed to configure scraper')
        return

    await scraper_instance.process_work_items()

if __name__ == '__main__':
    asyncio.run(run_instance())
