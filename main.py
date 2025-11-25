from playwright.sync_api import sync_playwright
from dataclasses import dataclass, asdict, field
import pandas as pd
import argparse
import os
import sys

@dataclass
class Business:
    """holds business data"""

    name: str = None
    address: str = None
    website: str = None
    phone_number: str = None
    reviews_count: int = None
    reviews_average: float = None
    latitude: float = None
    longitude: float = None


@dataclass
class BusinessList:
    """holds list of Business objects,
    and save to both excel and csv
    """
    business_list: list[Business] = field(default_factory=list)
    save_at = 'output'

    def dataframe(self):
        """transform business_list to pandas dataframe

        Returns: pandas dataframe
        """
        return pd.json_normalize(
            (asdict(business) for business in self.business_list), sep="_"
        )

    def save_to_excel(self, filename):
        """saves pandas dataframe to excel (xlsx) file

        Args:
            filename (str): filename
        """

        if not os.path.exists(self.save_at):
            os.makedirs(self.save_at)
        self.dataframe().to_excel(f"output/{filename}.xlsx", index=False)

    def save_to_csv(self, filename):
        """saves pandas dataframe to csv file

        Args:
            filename (str): filename
        """

        if not os.path.exists(self.save_at):
            os.makedirs(self.save_at)
        self.dataframe().to_csv(f"output/{filename}.csv", index=False)

def extract_coordinates_from_url(url: str) -> tuple[float,float]:
    """helper function to extract coordinates from url"""
    
    coordinates = url.split('/@')[-1].split('/')[0]
    # return latitude, longitude
    return float(coordinates.split(',')[0]), float(coordinates.split(',')[1])

def main():
    
    ########
    # input 
    ########
    
    # read search from arguments
    parser = argparse.ArgumentParser(description="Google Maps Scraper")
    
    # --- ADDED THE -l ARGUMENT AND MADE -s AND -l REQUIRED ---
    parser.add_argument("-s", "--search", type=str, help="The business type (e.g., 'dentist')", required=True)
    parser.add_argument("-l", "--location", type=str, help="The location to search in (e.g., 'london')", required=True)
    parser.add_argument("-t", "--total", type=int, help="Maximum number of listings to scrape (optional)")
    args = parser.parse_args()
    
    # Combine search and location into a single query for Google Maps
    full_search_query = f"{args.search.strip()} in {args.location.strip()}"
    search_list = [full_search_query]
    
    print(f"Executing search for: '{full_search_query}'")
    
    if args.total:
        total = args.total
    else:
        # if no total is passed, we set the value to random big number
        total = 1_000_000

    # Removed the 'input.txt' fallback logic to simplify for CLI usage.
    # If the user wants to use input.txt, they would run the script without 
    # the -s and -l arguments and modify the parsing logic above.
        
    ###########
    # scraping
    ###########
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        # NOTE: Using a placeholder URL that needs to be 'https://www.google.com/maps/'
        page.goto("https://www.google.com/maps/", timeout=60000) 
        # wait is added for dev phase. can remove it in production
        page.wait_for_timeout(5000)
        
        for search_for_index, search_for in enumerate(search_list):
            print(f"-----\n{search_for_index} - {search_for}".strip())

            # Fill the search box with the combined query
            # NOTE: The XPath for the searchbox input might change. 
            page.locator('//input[@id="searchboxinput"]').fill(search_for)
            page.wait_for_timeout(3000)

            page.keyboard.press("Enter")
            page.wait_for_timeout(5000)

            # scrolling
            # NOTE: This XPath is crucial for scrolling the results panel
            page.hover('//a[contains(@href, "/maps/place/")]') 

            # this variable is used to detect if the bot
            # scraped the same number of listings in the previous iteration
            previously_counted = 0
            while True:
                # Get the results pane element for controlled scrolling
                results_pane = page.locator('//div[@role="feed"]')
                results_pane.evaluate("node => node.scrollTop = node.scrollHeight") # Scroll to bottom

                page.wait_for_timeout(3000)
                
                # NOTE: Adjusted locator for listings to a more reliable structure
                listing_selector = '//a[contains(@href, "/maps/place/") and @aria-label]'

                current_count = page.locator(listing_selector).count()

                if current_count >= total:
                    listings = page.locator(listing_selector).all()[:total]
                    print(f"Total Scraped: {len(listings)}")
                    break
                else:
                    # logic to break from loop to not run infinitely
                    # in case arrived at all available listings
                    if current_count == previously_counted:
                        listings = page.locator(listing_selector).all()
                        print(f"Arrived at all available\nTotal Scraped: {len(listings)}")
                        break
                    else:
                        previously_counted = current_count
                        print(f"Currently Scraped: {current_count}")


            business_list = BusinessList()

            # scraping
            for listing in listings:
                try:
                    # Click on the listing to open the detail view
                    listing.click()
                    page.wait_for_timeout(5000)

                    # --- DETAIL VIEW XPATHS ---
                    name_attibute = 'aria-label'
                    address_xpath = '//button[@data-item-id="address"]//div[contains(@class, "fontBodyMedium")]'
                    website_xpath = '//a[@data-item-id="authority"]//div[contains(@class, "fontBodyMedium")]'
                    phone_number_xpath = '//button[contains(@data-item-id, "phone:tel:")]//div[contains(@class, "fontBodyMedium")]'
                    review_count_xpath = '//button[@jsaction="pane.reviewChart.moreReviews"]//span'
                    reviews_average_xpath = '//div[@jsaction="pane.reviewChart.moreReviews"]//div[@role="img"]'
                    
                    
                    business = Business()
                    
                    # Name is extracted from the listing element before the click
                    business.name = listing.get_attribute(name_attibute) or ""
                    
                    # Scrape Details
                    if page.locator(address_xpath).count() > 0:
                        business.address = page.locator(address_xpath).all()[0].inner_text()
                    else:
                        business.address = ""
                        
                    if page.locator(website_xpath).count() > 0:
                        business.website = page.locator(website_xpath).all()[0].inner_text()
                    else:
                        business.website = ""
                        
                    if page.locator(phone_number_xpath).count() > 0:
                        business.phone_number = page.locator(phone_number_xpath).all()[0].inner_text()
                    else:
                        business.phone_number = ""
                        
                    if page.locator(review_count_xpath).count() > 0:
                        review_text = page.locator(review_count_xpath).inner_text().split()[0].replace(',', '').strip()
                        business.reviews_count = int(review_text) if review_text.isdigit() else 0
                    else:
                        business.reviews_count = 0
                        
                    if page.locator(reviews_average_xpath).count() > 0:
                        average_text = page.locator(reviews_average_xpath).get_attribute(name_attibute).split()[0].replace(',','.').strip()
                        try:
                            business.reviews_average = float(average_text)
                        except ValueError:
                            business.reviews_average = 0.0
                    else:
                        business.reviews_average = 0.0
                    
                    
                    business.latitude, business.longitude = extract_coordinates_from_url(page.url)

                    business_list.business_list.append(business)
                except Exception as e:
                    print(f'Error occurred while scraping details: {e}')
                    
            
            #########
            # output
            #########
            filename_safe = full_search_query.replace(' ', '_').replace('/', '_')
            business_list.save_to_excel(f"google_maps_data_{filename_safe}")
            business_list.save_to_csv(f"google_maps_data_{filename_safe}")

        browser.close()


if __name__ == "__main__":
    main()