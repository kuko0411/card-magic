import urllib.request
from bs4 import BeautifulSoup
from unidecode import unidecode
import re
import sys
import json
import requests
import base64
import itertools
import sys
import collections
import solver

sys.setrecursionlimit(100000000)

base_url = "https://www.magiccardmarket.eu"

url = "https://www.magiccardmarket.eu/Products/Singles/Aether+Revolt/Glint-Sleeve+Siphoner"
location_re = re.compile(r"showMsgBox\(this,'Item location: ([^']*)'\)")

def parse_card_table(table):
    res = []

    for row in table.find_all("tr"):
        if "class" in row.attrs:
            continue 

        #print(str(row).encode("utf8"))
        for tag in row.contents:
            pass
            #print (str(tag).encode("utf8"))

        #print()
        #print(str(row.contents[0].span.contents[2]).encode("utf8"))
        #print()

        name = row.contents[0].span.contents[2].string
        url  = row.contents[0].span.contents[2].find("a")["href"]

        location = row.contents[0].span.contents[1].span["onmouseover"]
        location = location_re.match(location).group(1)

        price = row.find("td", class_= "st_price").div.div.string

        count = int(row.contents[6].string)

        # print("{:20}{:30}{:15}{:5}{:10}".format(name, url, location, price, count))

        #print (unidecode(name), unidecode(price))
        
        if not name or not price: 
            continue 

        res += [{
            "name": "" if not name else unidecode(name),
            "price": "" if not price else unidecode(price),
            "url": base_url + url,
            "location": location,
            "count": count
        }]


    return res


ajax_re = re.compile(r"jcp\('([^']*)'\+encodeURI\('([^']*)'\+moreArticlesForm.page.value\+'([^']*)'\)")

def fetch_card(url):
    print("Fetching", url, file=sys.stderr)
    with urllib.request.urlopen(url) as response:
        data = response.read()
        soup = BeautifulSoup(data, 'html.parser')

        name = soup.find("h1", class_ = "c-w nameHeader").text

        moreDiv = soup.find("div", id="moreDiv")

        tables = []

        if moreDiv:
            js = moreDiv["onclick"]
            match = ajax_re.search(js)

            head = match.group(1) + match.group(2)
            tail = match.group(3)

            for i in itertools.count():
                newurl = head + str(i) + tail
                
                print("{},".format(i), end=" ", file=sys.stderr)
                sys.stderr.flush()

                response = requests.post('https://www.magiccardmarket.eu/iajax.php', data={"args": newurl})
                encoded = response.text[67:-31]
                decoded = base64.b64decode(encoded).decode("utf8")

                if decoded == "0":
                    break

                tables += [BeautifulSoup(decoded, "html.parser")]

            print(file=sys.stderr)

        else:
            tables = [soup.find("table", class_ = "MKMTable fullWidth mt-40").tbody]
        
        res = []
        for table in tables:
            res += parse_card_table(table)

        return res
    return []

class Cardlist:
    url_single = "https://www.magiccardmarket.eu/Products/Singles"

    def __init__(self):
        ...

    @classmethod
    def fetch_single(cls, **params):
        response = requests.get(cls.url_single, params)
        print("Fetching", response.url, file=sys.stderr)

        soup = BeautifulSoup(response.text, 'html.parser')

        table = soup.find("table", class_="MKMTable fullWidth")
        res = []

        for link in table.find_all("a", href= lambda x: x.startswith("/Products")):
            res += [{
                "name": unidecode(link.string), 
                "url" : base_url + link["href"]
            }]

        return res

def fetch_cards(cardlist):
    for card in cardlist:
        card["sellers"] = fetch_card(card["url"])

def fetch_seller(url):
    print("Fetching", url)
    with urllib.request.urlopen(url) as response:
        data = response.read()
        soup = BeautifulSoup(data, 'html.parser')

        name = soup.find("span", typeof="v:Breadcrumb", property="v:title").text
        print ("Name", name, file=sys.stderr)

        url_list = soup.find("ul", class_=re.compile(".*catArticles-list.*"))
        cardlists = [(x.text, x["href"]) for x in url_list.find_all("a")]
        print(cardlists, file=sys.stderr)


class ShippingCost:
    url = "https://www.magiccardmarket.eu/Help/Shipping_Costs"

    ShippingDetail = collections.namedtuple("ShippingMethod", ["name", "certified", "max_value", "max_weight", "stamp_price", "price"])

    def __init__(self, src, dst):
        self.source = src
        self.destination = dst

    @classmethod
    def fetch(cls, src, dst):
        response = requests.post(cls.url, {"origin": src, "destination": dst})
        data = response.text

        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table", class_="MKMTable HelpShippingTable")

        methods = []

        for row in table.tbody.find_all("tr"):
            data = [cell.text for i, cell in enumerate(row.find_all(["th", "td"]))]
            
            # name = re.sub("[\(\[].*?[\)\]]", "", name)

            # print(name, file=sys.stderr)

            if len(data) < 5: continue
            if data[-1] == "": continue

            methods += [cls.ShippingDetail(*data)]
        
        result = cls(src, dst)
        result.methods = methods

        return result

    def groupby(self, f):
        return itertools.groupby(sorted(self.methods, key=f), key=f)

    def get_cheapest(self):
        return [
            
                sorted(data, 
                    key = lambda detail: int(detail.price.split()[0].replace(",", ""))
                )[0]
            
            for weight, data in self.groupby(
                lambda detail: int(detail.max_weight[:-2])
            )
        ]

    def __str__(self):
        return "Shiping({source} -> {destination}: {methods})".format(
            source = self.source,
            destination = self.destination,
            methods = list([x.name for x in self.methods])
        ) 

class ShippingManager:
    def __init__(self):
        self._fetch_mapping()
        self._cached = {}

    def _fetch_mapping(self):
        response = requests.get(ShippingCost.url)
        soup = BeautifulSoup(response.text, "html.parser")

        self._mapping_origin = {
            option.text: option["value"]
            
            for option in soup.find(
                "select", 
                {"name": "origin"}
            ).findChildren()
        }

        self._mapping_origin["Germany"] = "D"

        self._mapping_destination = {
            option.text: option["value"]
            
            for option in soup.find(
                "select", 
                {"name": "destination"}
            ).findChildren()
        }

    def get(self, src, dst, shorthands=False):
        if not shorthands:
            src = self._mapping_origin[src]
            dst = self._mapping_destination[dst]

        target = (src, dst)

        if target not in self._cached:
            print("Fetching shipping {} -> {}".format(src, dst), file=sys.stderr)
            self._cached[target] = ShippingCost.fetch(*target)
            
        return self._cached[target]



manager = ShippingManager()

# print(*manager.get("D", "SK", shorthands=True).get_cheapest(), sep="\n")

want = [
    # ("Polluted Mire", 4),
    # ("Snuff Out", 4),
    ("Bad Moon", 4)
]



data = []

for name, amount in want:
    card_url = Cardlist.fetch_single(name = name)[0]["url"]
    card_sellers = fetch_card(card_url)

    data += [{
        "name": name,
        "url": card_url,
        "sellers": card_sellers,
        "amount": amount
    }]



class Varlist:
    def __init__(self):
        self.location = "UNK"
        self.variables = []

    def __str__(self):
        return "Varlist(loc: {}, vars: {})".format(self.location, self.variables)

    def __repr__(self):
        return str(self)


vars = solver.Variables()

objective = 0
constraints = []

sellers = collections.defaultdict(Varlist) 

for card in data:
    total = 0

    for seller in card["sellers"]:
        x = vars.int("x", seller)
        
        name = seller["name"]
        sellers[name].location = seller["location"]
        sellers[name].variables += [x]

        constraints += [x <= seller["count"]]
        objective += (seller["price"].split()[0].replace(",", "") * x)
        total += x

    constraints += [total == card["amount"]]


# for i in range(1, x):
#     constraints += ["x{} >= 0".format(i)]

here = "Slovakia"
card_weight = 20

# print(*sellers.items(), sep="\n")

BIG = 9999

for name, varlist in sellers.items():
    variables = varlist.variables
    loc  = varlist.location

    shipping = manager.get(loc, here)

    last_price  = 0
    last_count = 1

    for cost in shipping.get_cheapest():
        price = int(cost.price.split()[0].replace(",", ""))

        y = vars.bool("y")

        objective += ((price - last_price) * y)

        constraints += [last_count * y  <= sum(variables)]
        constraints += [BIG * y >= (1 - last_count) + sum(variables)]

        last_count = int(cost.max_weight.split()[0]) // card_weight + 1
        last_price = price



problem = solver.make_lp(objective, constraints, vars)
file = "test2.mps"
# solver.write_mps(problem, file)
# res = solver.Gurobi().solve_mps(file)
print(res)

# print(*constraints, sep="\n")

# print(Shipping.fetch("IE", "SK"))

# s = "tdafm_ZFS%5DW%09%0Et%7Cv%60%7E_OoM%5B%5C%29%2C%27-%10%24%24%2B-%2A%2A%2A12755" + "," + str(9) + ",N;"  

# response = requests.post('https://www.magiccardmarket.eu/iajax.php', data={"args": s})
# print(response.text)
# encoded = response.text[67:-31]
# print(base64.b64decode(encoded))

# fetch_card("https://www.magiccardmarket.eu/Products/Singles/Saviors+of+Kamigawa/Scroll+of+Origins")

# cardlist = fetch_cardlist(url2)
# fetch_cards(cardlist)

# with open("out.json", "w") as out:
#     out.write(json.dumps(cardlist, sort_keys=True, indent=4))
# url3 = "https://www.magiccardmarket.eu/Users/Dragonegg"

# fetch_seller(url3)
