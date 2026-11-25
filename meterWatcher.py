'''
Use pyInstaller to make into a sharable exe:
   pyinstaller meterWatcher.py

'''

# Might be useful resources:
# https://www.androidpolice.com/how-to-allow-less-secure-apps-in-gmail
# https://support.google.com/accounts/answer/6010255?hl=en

# https://www.codingdojo.com/blog/what-is-web-scraping#:~:text=Also%20known%20as%20web%20data,job%20more%20quickly%20and%20efficiently.
import re 
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright, Page # conda install -c conda-forge playwright-python

DEBUG_MODE = False
import send_email
send_email.DEBUG_MODE = DEBUG_MODE
import dominate.tags as tags
from env_vars import EMAIL, PASSWORD, RECEIVE_EMAIL # KMPUD Login, and address to receive email
# For Debugging
# import json

LOGIN_URL = 'https://www.kmpud.com/login/'
METER_URL = 'https://www.kmpud.com/my-account/meter-information/'

def _get_meter_data(page: Page) -> dict:
    ''' After program has already logged in, this function locates and returns the month's data for every meter type available on the kmpud utility website.
        ex: ('Water', 'Electric', 'Propane')
        page: the logged-in Playwright Page

        Returns a dict of the form:
        {'Meter Type': {'Unit': unit,
                        'Data': list of usage data,
                        'Dates': list of dates}
        } for every meter type.
    '''
    # First navigates to monthly usage, so that all the monthly data will appear in a <script> tag,
    # which happens to be the last one in the document
    _navigate_monthly(page)

    # Now that the monthly usage has been selected, the data appears in the javascript.
    # text_content() gives the javascript contained in the <script> tag
    # (works on hidden elements like <script>, unlike inner_text())
    script = page.locator('#page > script:last-of-type').text_content()
    if DEBUG_MODE: print(script)

    #    The script has a lot of JSON in it, and the important data is contained in this JSON.
    #    Since the JSON is not complex, regular expressions pull out the pieces needed.
    pattern = re.compile(r"""\"(?P<MeterType>\w*?)\ Meter.*?   # (?P<MeterType>...) is a named capture group
                         categories\":\[(?P<Dates>.*?)\].*?  # .*? at the end takes care of stuff in between the text of interest
                         text\":\"(?P<Unit>.*?)\".*?
                         data\":\[(?P<Data>.*?)\]""", re.VERBOSE)
    meter_data = {}
    for matchObj in pattern.finditer(script):
        meter_data[matchObj.group('MeterType')] = {'Unit': matchObj.group('Unit'),
                                                   'Data': matchObj.group('Data').split(','),
                                                   'Dates': matchObj.group('Dates').replace('"', '').split(',')}
    return meter_data


def _navigate_monthly(page: Page) -> None:
    '''Navigates to monthly usage, causing all monthly data to appear in a <script> tag,
         which happens to be the last one in the document.
       This includes every meter's monthly data.'''
    # There are multiple <a> tags with the text 'Monthly'.
    # Any of the ones ending in the word 'Monthly' will work; .first takes the first one.
    monthly_link = page.locator('a').filter(has_text=re.compile(r'Monthly\s*$')).first
    href = monthly_link.get_attribute('href')
    page.goto(urljoin(page.url, href))


# ==========================================================
# For crafting the email
def html_table(meter_data):
    '''
    Produces an html table containing the meter data.
    Rows are different days, columns are different meters.
    '''
    dates = clean_format(meter_data)
    html = tags.html()
    html.add(tags.head(tags.style(
        'th, td {\n\tpadding: 10px;\n}\n\n')))
        # 'tr:nth-child(even) {\n\tbackground-color:rgb(146, 232, 232);\n}' # Doesn't seem to work for email
    body = html.add(tags.body())
    table = body.add(tags.table())
    rows = table.add([tags.tr() for _ in range(len(dates)+1)])
    # Dates Column
    rows[0].add([tags.th("Date")]) # Table Header
    for i, date in enumerate(dates[::-1]):
        rows[i+1].add(tags.td(date))
    # Meter Usage Columns
    for meter_type, info in meter_data.items(): 
        rows[0].add(tags.th(f'{meter_type} ({info['Unit']})')) # Table Header
        for i, val in enumerate(info['Data'][::-1]):
            rows[i+1].add(tags.td(val))
    return str(html)

def clean_format(meter_data, placeholder = '-'):
    '''This ensures that all of the meter's data lists are the same length, 
    with placeholders for missing data. Ensures that the list 
    of dates for each meter is the same, without skipping over days. 
    Returns the list of dates for easy access.'''
    # Assumes only data within one month is included.
    # Assumes that dates are in order
    meter_types = list(meter_data.keys())
    month, _ = meter_data[meter_types[0]]['Dates'][0].split('-')
    # Find the last day that has data
          # ".split('-')[-1]" extracts the day from the "month-day" format
    last_days = [int(meter_data[meter]['Dates'][-1].split('-')[-1]) for meter in meter_types]
    last_day = max(last_days)
    clean_dates = [f'{month}-{day}' for day in range(1, last_day+1)]
    for meter in meter_types:
        clean_data = []
        # Days that have data
        dates = meter_data[meter]['Dates']
        data_days = list(map(lambda date : int(date[len(month)+1:]), dates))
        prev = 0
        for index in range(len(data_days)):
            day = data_days[index]
            if day > prev+1:
                # If it's not consecutive, add empty string placeholders for the missing data
                clean_data.extend([placeholder] * (day - prev-1))
            clean_data.append(meter_data[meter]['Data'][index])
            prev = day
        if last_day > day:
            clean_data.extend([placeholder] * (last_day - day))

        meter_data[meter]['Data'] = clean_data
        meter_data[meter]['Dates'] = clean_dates
    return clean_dates


    # Missing data means there will be a different number of data points for different meters.
    # This finds the count for the meter with the least missing data.
    count = max([len(meter_data[meter]['Data']) for meter in meter_data])


# __________________________________________________________
#                     Driver Code
# ==========================================================
# Getting the meter data from kmpud.com
# ==========================================================

with sync_playwright() as p:
    # headless=False shows the browser window, which helps while debugging
    browser = p.chromium.launch(headless=not DEBUG_MODE)
    page = browser.new_page()
    page.goto(LOGIN_URL)

    # Same form RoboBrowser found: the one whose action is the login URL
    form = page.locator(f'form[action="{LOGIN_URL}"]')
    if DEBUG_MODE: print('Log in HTML form: \n', form.evaluate('el => el.outerHTML'))

    form.locator('input[name="log"]').fill(EMAIL)
    form.locator('input[name="pwd"]').fill(PASSWORD)
    form.locator('input[name="pwd"]').press('Enter')  # submits the form like a user would

    # Wait until we've left the login page (times out if login fails)
    page.wait_for_url(lambda url: '/login' not in url)
 
    # Login cookies live in the browser context, so going straight to the URL stays logged in
    page.goto(METER_URL)
    
    # Could use this to click on the element instead:
    # page.locator(f'a[href="{METER_URL}"]').first.dispatch_event('click')
    # page.wait_for_load_state()

    # Scrape the meter data from the page.
    meter_data = _get_meter_data(page)
    # Some meter data may be missing so there will be a different number of data points for different meters.
    # This finds the count for the meter with the least missing data.
    count = max([len(meter_data[meter]["Data"]) for meter in meter_data])

    browser.close()



if DEBUG_MODE: print('Meter Data: \n', meter_data)

# if DEBUG_MODE:
#     with open('temp_save.txt', 'w') as file:
#         file.write(json.dumps({'Dates': dates,
#                                'Meter': meter_data}))

# Debugging
# import json

# with open('temp_save.txt') as text:
#     dic = json.load(text)

# dates = dic['Dates']
# meter_data = dic['Meter']

# ================================================================
#                   Sending the information by email:
# ================================================================

# ===================== Crafting the message: ========================

# ---------------- Subject --------------------
if count >= 2:
    # the slash at the end means ignore the line feed in the string
    subject = f"Last two days usage - Water ({meter_data['Water']['Unit']}): {meter_data['Water']['Data'][-2]}, {meter_data['Water']['Data'][-1]}\
         - Electricity ({meter_data['Electric']['Unit']}): {meter_data['Electric']['Data'][-2]}, {meter_data['Electric']['Data'][-1]}"
else:
    # the slash at the end means ignore the line feed in the string
    subject = f"Yesterday's usage: - Water ({meter_data['Water']['Unit']}): {meter_data['Water']['Data'][0]}\
         - Electricity ({meter_data['Electric']['Unit']}): {meter_data['Electric']['Data'][0]}"

# ----------------- Body ---------------------
message = html_table(meter_data)

if DEBUG_MODE: print(message)

# ============================ Sending Message =================================

receiver_address = RECEIVE_EMAIL
# receiver_address = 'meterWatcher@gmail.com'
send_email.send(subject, message, receiver_address)
