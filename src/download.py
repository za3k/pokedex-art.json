import requests
import sqlitedict
import json
import time
from tqdm import tqdm
from bs4 import BeautifulSoup
from pprint import pprint
from pathlib import Path

cache = sqlitedict.SqliteDict("data/requests.sqlite")

def fetch(url):
    if url not in cache:
        response = requests.get(url, headers = {
            "User-Agent": "za3k@za3k.com",
        })
        if response.status_code == 429:
            time.sleep(int(response.headers.get('Retry-After')))
            return fetch(url)
        elif response.status_code == 404:
            data = ""
        else:
            response.raise_for_status()
            data = response.content

        time.sleep(0.2)
        cache[url] = data
        cache.commit()

    return cache[url]

def main():
    r = fetch("https://pokemondb.net/pokedex/all")
    soup = BeautifulSoup(r, "html.parser")
    last = None, None
    dex = []
    l = tqdm(soup.select("#pokedex > tbody > tr"))
    for row in l:
        number = row.select_one("td:nth-child(1) .infocard-cell-data").text
        name = row.select_one(".ent-name").text.strip()
        link = row.select_one(".ent-name")["href"]
        id_ = link.split("/")[-1]
        data = {"number": number, "name": name, "id": id_}
        l.set_description(f"{number}/1025: {name}")

        if last == (number, name): continue # Skip duplicate entries, such as for mega-evolutions
        last = (number, name)

        pokedex_html = fetch(f"https://pokemondb.net/pokedex/{id_}")
        art_html = fetch(f"https://pokemondb.net/artwork/{id_}")

        # Pokedex
        soup = BeautifulSoup(pokedex_html, "html.parser").select_one("#main")
        def vital_stat(x):
            for r in soup.select(".vitals-table > tbody > tr"):
                if r.select_one("th:nth-child(1)").text == x:
                    return r.select_one("td:nth-child(2)")

        assert data["number"] == vital_stat("National №").text
        data["species"] = vital_stat("Species").text
        data["type"] = sorted(x.text for x in vital_stat("Type").select("a"))
        data["height"] = vital_stat("Height").text
        data["weight"] = vital_stat("Weight").text
        for h in soup.find_all("h2"):
            if h.text == "Pokédex entries":
                pokedex = h.find_next_sibling("div")
                data["pokedex"] = pokedex.select_one("td.cell-med-text").text
                data["pokedex_full"] = {}
                for entry in pokedex.select("tr"):
                    data["pokedex_full"][
                        "/".join(game.text for game in entry.select("th .igame"))
                    ] = entry.select_one("td").text
                break

        # [todo 2. evolution (.infocard-list-evo), mega evolution]

        # Sprite links, which games have the pokemon
        data["art"] = {}
        data["gens"] = []
        gens = [int(e.text.removeprefix("Generation ")) for e in soup.select(".sprites-table > thead th:nth-child(n+2)")]
        for gen, e in zip(gens, soup.select(".sprites-table > tbody > tr:nth-child(1) > td:nth-child(n+2)")):
            if x := e.select_one("a"):
                data["art"][f"Sprite gen {gen}"] = x['href']
                data["gens"].append(gen)
        for gen, e in zip(gens, soup.select(".sprites-table > tbody > tr:nth-child(2) > td:nth-child(n+2)")):
            if x := e.select_one("a"):
                data["art"][f"Sprite gen {gen} shiny"] = x['href']

        # Art
        soup = BeautifulSoup(art_html, "html.parser").select_one("#main")
        for e in soup.select(".grid-col"):
            which = e.select_one("strong").text
            animal = e.select_one(".text-muted").text
            link = e.select_one("img")['src']
            if animal.endswith("- Gigantamax"):
                animal = animal.removesuffix(" - Gigantamax")
                which = f"Gigantamax: {which}"
            if animal.startswith("Mega "):
                animal = animal.removeprefix("Mega ")
                which = f"Mega: {which}"
            if animal != data["name"]:
                animal, which = data["name"], f"{animal}: {which}"
            data["art"][which] = link

        for link in data["art"].values():
            # Download the pictures
            path = Path("data") / link.removeprefix("https://img.pokemondb.net/")
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                content = fetch(link)
                with open(path, "wb") as f:
                    f.write(content)
        data["art"] = { k: v.removeprefix("https://img.pokemondb.net/") for k,v in data["art"].items() }

        dex.append(data)

    with open("data/pokedex.json", "w", encoding="utf8") as f:
        json.dump(dex, f)

if __name__ == '__main__':
    main()
