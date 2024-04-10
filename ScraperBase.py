import requests
import time
import asyncio
from enum import Enum
import typing


class WorkItemType(Enum):
    CRAWL = 'CRAWL'
    NOOP = 'NOOP'
    SCRAPE = 'SCRAPE'
    STREAM = 'STREAM'
    HEALTHCHECK = 'HEALTHCHECK'


NOOP_TIMEOUT = 5
WORK_ITEM_PROGRESS_INTERVAL = 60

# SWAGGER https://scraper-scraper-main.kube.agrp.dev/swagger-ui/index.html

BE_URL = 'https://scraper-scraper-main.kube.agrp.dev/rest/v2/control/'

ENDPOINTS = {
    'WORK_ITEM_PROGRESS': 'workItemProgress',
    'WORK_ITEM_FAILED': 'workItemFailed',
    'WORK_ITEM_COMPLETED': 'workItemCompleted',
    'SEND_EMAIL': 'sendEmail',
    'RECIEVE_SCRAPING_ERRORS': 'receiveScrapingErrors',
    'RECIEVE_SCRAPER_TARGETS': 'receiveScraperTargets',
    'RECIEVE_SCRAPER_RECORDS': 'receiveScraperRecords',
    'RECIEVE_HEALTH_CHECK_INFO': 'receiveHealthcheckInfo',
    'RECIEVE_FILE': 'receiveFile',
    'FILE_EXISTS': 'fileExists',
    'FILE': 'file',
    'REGISTER': 'register',
    'NEXT_WORK_ITEM': 'getNextWorkItem',
}


class BaseScraper:
    def __init__(self, custom_id, api_key):
        self.custom_id = custom_id
        self.api_key = api_key
        self.details = {}
        self.instance_id = hash(time.time())

    async def init(self):
        response = await self.fetch('REGISTER', queryParams={'customId': self.custom_id}, errorMessage='Failed to register scraper')
        data = response.json()
        print('Scraper register:', data)
        if response.status_code != 200:
            return False

        self.details = data['scraper']

        if not self.details['enabled']:
            print('Scraper is disabled')
            return False
        if not data['configured']:
            print('Scraper is not configured')
            return False
        return True

    async def process_crawl_item():
        raise NotImplementedError('not implemented')

    async def process_scrape_item():
        raise NotImplementedError('not implemented')

    async def process_stream_item():
        raise NotImplementedError('not implemented')

    async def process_health_check_item():
        raise NotImplementedError('not implemented')

    async def process_work_items(self):
        while True:
            await self.get_next_work_item()

    async def get_next_work_item(self):
        response = await self.fetch('NEXT_WORK_ITEM', queryParams={'scraperId': self.details['id'], 'instanceId': str(self.instance_id)})
        work_item = response.json()
        work_item_type = work_item['workItemType']
        print('Got work item', work_item_type)

        if work_item_type == WorkItemType.NOOP.value:
            await asyncio.sleep(NOOP_TIMEOUT)
            return

        progress_task = asyncio.create_task(self.work_item_progress(work_item))

        if work_item_type == WorkItemType.SCRAPE.value:
            await asyncio.create_task(self.process_scrape_item(work_item))
        elif work_item_type == WorkItemType.CRAWL.value:
            await asyncio.create_task(self.process_crawl_item(work_item))
        elif work_item_type == WorkItemType.STREAM.value:
            await asyncio.create_task(self.process_stream_item(work_item))
        elif work_item_type == WorkItemType.HEALTHCHECK.value:
            await asyncio.create_task(self.process_health_check_item(work_item))
        else:
            print('Unsupported work item type', work_item_type)

        progress_task.cancel()

    async def fetch(self, endpoint, path='', queryParams=None, method='GET', body=None, errorMessage=''):
        url = f'{BE_URL}{ENDPOINTS[endpoint]}'
        if path:
            url += '/' + path
        if queryParams:
            url += '?' + \
                '&'.join([f'{key}={value}' for key,
                         value in queryParams.items()])

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }

        response = requests.request(method, url, headers=headers, json=body)
        if response.status_code != 200:
            print(errorMessage, response.json(), {'body': body})
        return response

    async def work_item_progress(self, work_item):
        while True:
            print('Progressing work item', work_item['id'])
            await self.fetch('WORK_ITEM_PROGRESS', method='POST', queryParams={'instanceId': str(self.instance_id), 'workItemId': work_item['id']})
            await asyncio.sleep(WORK_ITEM_PROGRESS_INTERVAL)

    async def send_scrape_targets(self, metadata_list):
        return await self.fetch('RECIEVE_SCRAPER_TARGETS', method='POST', body=[{'sourceId': self.details['id'], 'metadata': metadata} for metadata in metadata_list], errorMessage='Failed to send scrape targets')

    async def send_scrape_records(self, records):
        return await self.fetch('RECIEVE_SCRAPER_RECORDS', queryParams={'scraperId': self.details['id']}, method='POST', body=records, errorMessage='Failed to send scrape records')

    async def work_item_completed(self, work_item):
        return await self.fetch('WORK_ITEM_COMPLETED', queryParams={'instanceId': str(self.instance_id), 'workItemId': work_item['id']}, method='POST', errorMessage='Failed to report work item completion')

    async def work_item_failed(self, work_item, error):
        return await self.fetch('WORK_ITEM_FAILED', queryParams={'instanceId': str(self.instance_id)}, method='POST', body={'workItemId': work_item['id'], 'msgs': [{'msg': str(error), 'stacktrace': error.__traceback__}]}, errorMessage='Failed to report work item failure')

    async def send_email(self, receiver: str, subject: str, content: str):
        return await self.fetch('SEND_EMAIL', method='POST', body={'emailAddressesTo': [receiver], 'subject': subject, 'content': content}, errorMessage='Failed to send email')

    async def get_file(self, file_name: str):
        response = await self.fetch('FILE', path=self.details['id'], queryParams={'fileName': file_name}, errorMessage='Failed to get file')
        return response.content

    async def file_exists(self, file_name: str):
        response = await self.fetch('FILE_EXISTS', path=self.details["id"], queryParams={'fileName': file_name}, errorMessage='Failed to check if file exists')
        return response.json()

    async def send_file(self, file):
        files = {'file': file}
        response = requests.post(f'{BE_URL}{ENDPOINTS["RECIEVE_FILE"]}?fileStoreId={self.details["id"]}', files=files, headers={
                                 'Authorization': f'Bearer {self.api_key}'})
        if response.status_code != 200:
            print('Failed to send file', response.json())
        return response

    async def send_scraping_errors(self, errors):
        return await self.fetch('RECIEVE_SCRAPING_ERRORS', method='POST', queryParams={'scraperId': self.details['id']}, body=errors, errorMessage='Failed to receive scraping errors')

    async def send_health_check_info(self, state: typing.Literal['GREEN', 'AMBER', 'RED', 'GREY'], message: str):
        return await self.fetch('RECIEVE_HEALTH_CHECK_INFO', method='POST', body={'scraperId': self.details['id'], 'metadata': {'message': message}, 'state': state}, errorMessage='Failed to receive scraping errors')
