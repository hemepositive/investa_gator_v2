import lxml.html
import requests
from unidecode import unidecode
import time
import random
import datetime
import json
from textblob.classifiers import NaiveBayesClassifier as NBC
from textblob.classifiers import DecisionTreeClassifier as DTC
from textblob import TextBlob
import os
import pickle
from models import CRUD,Ads,TrainData,KeyWords



#a web scraper, for local computation
#At present, this seems to work fine
class Scraper:
    def __init__(self,
                 base_urls=[
                     "http://newyork.backpage.com/FemaleEscorts/",
                     "http://newyork.backpage.com/BodyRubs/",
                     "http://newyork.backpage.com/Strippers/",
                     "http://newyork.backpage.com/Domination/",
                     "http://newyork.backpage.com/TranssexualEscorts/",
                     "http://newyork.backpage.com/MaleEscorts/",
                    "http://newyork.backpage.com/Datelines/",
                     "http://newyork.backpage.com/AdultJobs/"
                 ],
                 child_keywords=[],
                 trafficking_keywords=[]
    ):
        self.base_urls = base_urls
        self.child_keywords = child_keywords
        self.trafficking_keywords = trafficking_keywords

    def letter_to_number(self,text):
        text= text.upper()
        text = text.replace("ONE","1")
        text = text.replace("TWO","2")
        text = text.replace("THREE","3")
        text = text.replace("FOUR","4")
        text = text.replace("FIVE","5")
        text = text.replace("SIX","6")
        text = text.replace("SEVEN","7")
        text = text.replace("EIGHT","8")
        text = text.replace("NINE","9")
        text = text.replace("ZERO","0")
        return text

    def verify_phone_number(self,number):
        data = pickle.load(open("twilio.creds","r"))
        r = requests.get("http://lookups.twilio.com/v1/PhoneNumbers/5165789423",auth=data)
        if "status_code" in json.loads(r.content).keys():
            return False
        else:
            return True
        
    def phone_number_parse(self,values):
        values["phone_number"] = []
        text = self.letter_to_number(values["text_body"])
        phone = []
        counter = 0
        found = False
        possible_numbers = []
        for ind,letter in enumerate(text):
            if letter.isdigit():
                phone.append(letter)
                found = True
            else:
                if found:
                    counter += 1
                if counter > 15 and found:
                    phone = []
                    counter = 0
                    found = False

            if len(phone) == 10 and phone[0] != '1':
                possible_numbers.append(''.join(phone))
                phone = [] #consider handling measurements
            if len(phone) == 11 and phone[0] == '1':
                possible_numbers.append(''.join(phone))
                phone = [] #consider handling measurements
        for number in possible_numbers:
            if self.verify_phone_number(number):
                values["phone_number"].append(number)
        return values
    
    def scrape(self,links=[],auto_learn=False,long_running=False,translator=False):
        responses = []
        values = {}
        data = []

        if links == []:
            for base_url in self.base_urls:
                r = requests.get(base_url)
                text = unidecode(r.text)
                html = lxml.html.fromstring(text)

                links = html.xpath("//div[@class='cat']/a/@href")
                for link in links:
                    if len(self.base_urls) > 1 or len(self.base_urls[0]) > 3:
                        time.sleep(random.randint(1,2))
                        if long_running:
                            time.sleep(random.randint(5,27))
                    try:
                        responses.append(requests.get(link))
                        print link
                    except requests.exceptions.ConnectionError:
                        print "hitting connection error"
                        continue
        else:
            for link in links:
                if len(self.base_urls) > 1 or len(self.base_urls[0]) > 3:
                    time.sleep(random.randint(1,2))
                    if long_running:
                        time.sleep(random.randint(5,17))
                try:
                    responses.append(requests.get(link))
                    print link
                except requests.exceptions.ConnectionError:
                    print "hitting connection error"
                    continue

        for r in responses:
            text = r.text
            html = lxml.html.fromstring(text)
            values["title"] = html.xpath("//div[@id='postingTitle']/a/h1")[0].text_content()
            values["link"] = unidecode(r.url)
            values["new_keywords"] = []
            try:
                values["images"] = html.xpath("//img/@src")
            except IndexError:
                values["images"] = "weird index error"
            pre_decode_text = html.xpath("//div[@class='postingBody']")[0].text_content().replace("\n","").replace("\r","")  
            values["text_body"] = pre_decode_text 
            try:
                values["posted_at"] = html.xpath("//div[class='adInfo']")[0].text_content().replace("\n"," ").replace("\r","")
            except IndexError:
                values["posted_at"] = "not given"
            values["scraped_at"] = str(datetime.datetime.now())
            body_blob = TextBlob(values["text_body"])
            title_blob = TextBlob(values["title"])
            values["language"] = body_blob.detect_language() #requires the internet - makes use of google translate api
            values["polarity"] = body_blob.polarity
            values["subjectivity"] = body_blob.sentiment[1]
            translated = translator or values["language"] == "es" #this is bad, fix this.
            if translated:
                values["translated_body"] = body_blob.translate(from_lang="es")
                values["translated_title"] = title_blob.translate(from_lang="es")
            else:
                values["translated_body"] = "none"
                values["translated_title"] = "none"
            text_body = values["text_body"]
            title = values["title"]

            #why is this a boolean?
            if translated:
                text_body = values["translated_body"]
                title = values["translated_title"]

            if auto_learn:
                train_crud = CRUD("sqlite:///database.db",TrainData,"training_data")
                train = train_crud.get_all() 
                train = [(elem.text,"trafficking") for elem in train]
                #to do: add data for not trafficking
                cls = []
                cls.append(NBC(train))
                cls.append(DTC(train))

                #increase this number, replace this with something reasonable.
                trk_count = 0
                for cl in cls:
                    if cl.classify(text_body) == "trafficking":
                        trk_count += 1

                #this is hacky at best
                if float(trk_count)/len(cls) > 0.5:
                    train_data = TrainData()
                    train_data.text = values["text_body"]
                    train_crud.insert(train_data)
                    values["trafficking"] = "found"
                else:
                    values["trafficking"] = "not_found"
                #To do set up google alerts here
                #This should be easy..
            else:
                values["trafficking"] = "not_found"

            #why am I doing this?
            #the point of this is to keep track of keywords that are passed in from the user.
            #perhaps this should stay?
            values["child_urls"] = []
            for keyword in self.child_keywords:
                if keyword in text_body:
                    values["child_urls"].append(values["link"])
                elif keyword in title:
                    values["child_urls"].append(values["link"])

            values["trafficking_urls"] = []
            for keyword in self.trafficking_keywords:
                if keyword in text_body:
                    values["trafficking_urls"].append(values["link"])
                elif keyword in title:
                    values["trafficking_urls"].append(values["link"])

            #this looks fine...
            values["new_keywords"].append(self.pull_keywords(text_body))
            values["new_keywords"].append(self.pull_keywords(title))
            values = self.phone_number_parse(values)
            #this might need to stay until I can figure out how to
            #pass python datastructures to postgres...
            #also, there maybe another way to deal with this generally....perhaps a database that acts like a dictionary?
            #perhaps I could use mongo here...
            numbers = pickle.load(open("numbers.p","rb"))
            values["network"] = []
            for network in numbers.keys():
                if values["phone_number"] in numbers[network]:
                    values["network"].append(network)
            data.append(values)
        self.save_ads(data)#to do, replace this with database calls
        return data

    def pull_keywords(self,text):
        #to do, get a list of common words we don't care about and use those instead of this terrible hacking thing
        #this is terrible, fix it!!!
        text = text.lower()
        ignore_words = ["and","or","to","an","to","like","all","am","your","I","who"," ",'']
        new_text = []
        for word in text.split(" "):
            if not word in ignore_words:
                new_text.append(word)
        return new_text

    def save_ads(self,data):
        crud = CRUD("sqlite:///database.db",table="ads")
        
        for datum in data:
            ad = Ads()
            ad.title=datum["title"],
            ad.phone_number=datum["phone_number"],
            ad.text_body=datum["text_body"],
            ad.photos=json.dumps(datum["images"]),#change this so I'm saving actual pictures to the database.
            ad.link=datum["link"],
            ad.posted_at = datum["posted_at"],
            ad.scraped_at=datum["scraped_at"],
            ad.flagged_for_child_trafficking=json.dumps(datum["child_urls"]),
            ad.flagged_for_trafficking=json.dumps(datum["trafficking_urls"]),
            ad.language=datum["language"],
            ad.polarity=datum["polarity"],
            ad.translated_body=datum["translated_body"],
            ad.translated_title=datum["translated_title"],
            ad.subjectivity=datum["subjectivity"],
            ad.network=json.dumps(datum["network"]),
            crud.insert(ad)
            
if __name__ == '__main__':
    scraper = Scraper(base_urls=["http://newyork.backpage.com/FemaleEscorts/"])
    data = scraper.scrape()
    
    
