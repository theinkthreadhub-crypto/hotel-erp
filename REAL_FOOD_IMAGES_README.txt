Foodpiolet: Real Food Photos (not AI-generated artwork)

1. Extract the ZIP to a Windows folder.
2. Install Python 3.10+ from python.org.
3. Open CMD in the extracted folder.
4. Run: py -m pip install requests pillow
5. Run: py download_real_food_photos.py

Downloads 240x240-pixel compressed JPG food photos from Wikimedia Commons where search results contain all relevant dish-name words. This is only a matching heuristic, not a guarantee that the image depicts the requested dish. Not all 500 dishes will have available matches. Failed/missing dishes are logged instead of replaced with incorrect pictures.

Outputs:
- Foodpiolet_Real_Food_Images/ (downloaded thumbnails)
- Foodpiolet_Real_Photo_Licenses_And_Status.csv (creator, URL, license and download status)
- Foodpiolet_Real_Photos.zip (all downloaded photos and their credits)

IMPORTANT: Before business use, verify photo/dish match and each image's license/attribution requirements. Some CC licenses require credits, source link, or share-alike terms. Do not re-upload third-party restaurant images without permission.
