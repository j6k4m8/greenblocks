<h1 align=center>Green Blocks</h1>

a [wordle](https://www.powerlanguage.co.uk/wordle/) clone, for when you NEED to have another wordle NOW

<p align=center><img width="300" alt="image" src="https://user-images.githubusercontent.com/693511/148559904-9717e2b1-c4ce-4db5-afbd-f177ac6967c3.png"></p>

## tour of the codebase

There are two files — a server (HTTP API) written in Flask (`app.py`) and the web application front-end code (`templates/index.html`) written in Vue.js.

The flask website uses a unique, client-generated ID to keep track of games. The Vue application receives full game state on every request, and uses this to rerender the game board and keyboard as appropriate.

## dataset generation

The list of common words in `common5.txt` was derived from [this page](https://raw.githubusercontent.com/first20hours/google-10000-english/master/google-10000-english-usa-no-swears-short.txt), filtering on five-letter words. I manually removed proper nouns as I found them, and truncated the list to the first (i.e., most common) 1000 or so words.

The complete wordlist (all valid guess words) was generated using:

```python
import json

# https://github.com/barrust/pyspellchecker/blob/master/spellchecker/resources/en.json.gz
all_words = json.load(open('en.json'))

all_words_len_five = [
    word for word in all_words.keys() if len(word) == 5
]

with open("wordlist.txt", "w") as f:
    for word in all_words_len_five:
        f.write(word + "\n")
```
