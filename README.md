<h1 align=center>Green Blocks</h1>

<p align=center>a <a href="https://www.powerlanguage.co.uk/wordle/">Wordle</a> clone, for when you NEED to have another wordle NOW</p>

<p align=center><img width="300" alt="image" src="https://user-images.githubusercontent.com/693511/148559904-9717e2b1-c4ce-4db5-afbd-f177ac6967c3.png"></p>

## features

* keyboard coloring
* tap to edit boxes out of order
* customizable wordlists


## tour of the codebase

There are two files — a server (HTTP API) written in Flask (`app.py`) and the web application front-end code (`templates/index.html`) written in Vue.js.

The flask website uses a unique, client-generated ID to keep track of games. The Vue application receives full game state on every request, and uses this to rerender the game board and keyboard as appropriate.

### server

The server has two main elements: A `Game` object, which handles playing a game, scoring guesses, and letting you know when you're out of guesses; and a `GameStatePersister`. I've written two `GameStatePersister`s, which you can switch in and out depending on your preferences:

* `JSONFileGameStatePersister` stores games in a JSON file on the local machine; this is good for debugging
* `DynamoDBGameStatePersister` stores the game states in a DynamoDB database in AWS. This is what is used for production workloads.

You can also implement your own by implementing the `save_game` and `load_game` methods.

The `Game` object can be used in isolation from the rest of the code. For example, you could play a game in the terminal:

```python
>>> from app import Game
>>> g = Game()
>>> g.guess("frogs")
[ your score here ]
```

The biggest "gotcha" of the backend code is the scoring mechanism, which requires two passes in order to make sure we're not accidentally scoring the same letter more times than it appears in the answer. (For example, if the answer is `CADDY` and we guess `DROPS`, only ONE of the `D` letters in the guess should be scored as "incorrect location"; the other should be a grey "wrong letter" tile.)

(Note that games played like this will not be persisted to the GameStatePersister of choice.)

### frontend

The game is written as a fully standalone single HTML page: When the page loads, the app looks for a unique UUID stored in `localStorage`. If it can't find it, a new one is generated. Then, the application holds onto this as the player's identity. (The `GameStatePersister` uses this to keep track of games for a user in between requests.)

First, the server is polled for an `IN_PROGRESS` game with the player's UUID. If none is found, we don't create one yet: We wait for the user to submit their first guess. (In other words, we don't have any games stored in the database with zero guesses; this prevents db bloat from lots of users hitting the page and never playing.) After each guess, we send the latest guess to the server. The server responds from the `_game_endpoint` function, either reading in the latest game state from the database, or creating a new one if this is the first guess. (In other words, there is no "correct" answer yet on a player's first guess.)

The tiles are a simple rendering of the game state; the most interesting thing happening on the frontend is the rendering of the keyboard tiles, which is done each time the game state updates.

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
