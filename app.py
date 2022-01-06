from typing import Any, Callable
from enum import Enum
import random
from functools import cache


import abc
import os
import json
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import boto3
from boto3.dynamodb.conditions import Key


class Wordlist:
    def __init__(self, filename: str = "/usr/share/dict/words"):
        self.filename = filename

    @cache
    def get_words(self):
        with open(self.filename) as f:
            return f.read().splitlines()

    @cache
    def words_of_length(self, length: int):
        return [word for word in self.get_words() if len(word) == length]

    def __contains__(self, word: str):
        return word in self.get_words()

    def get_random_word(self, length: int = None):
        if length is None:
            return random.choice(self.get_words())
        else:
            return random.choice(self.words_of_length(length))


class Score(str, Enum):
    INCORRECT_LETTER = "INCORRECT_LETTER"
    WRONG_LOCATION = "WRONG_LOCATION"
    CORRECT = "CORRECT"
    INVALID_GUESS = "INVALID_GUESS"
    OUT_OF_GUESSES = "OUT_OF_GUESSES"
    NOT_A_WORD = "NOT_A_WORD"


# common5.txt in the same directory as this file
wordlist = Wordlist(filename=os.path.join(os.path.dirname(__file__), "common5.txt"))
all_valid_words = Wordlist(
    filename=os.path.join(os.path.dirname(__file__), "wordlist.txt")
)


class Game:
    def __init__(
        self,
        answer: str = None,
        number_of_guesses: int = 6,
        guesses_remaining: int = None,
        guesses: Any = None,
        scores: Any = None,
    ):
        self._number_of_guesses = number_of_guesses
        self._guesses_remaining = guesses_remaining or number_of_guesses
        self._guesses = guesses or []
        self._scores = scores or []
        self._answer = answer or wordlist.get_random_word(length=5)

    @staticmethod
    def from_game_state(game_state: dict):
        return Game(
            answer=game_state["answer"],
            number_of_guesses=game_state["number_of_guesses"],
            guesses_remaining=game_state["guesses_remaining"],
            guesses=game_state["guesses"],
            scores=game_state["scores"],
        )

    def to_game_state(self):
        return {
            "answer": self._answer,
            "number_of_guesses": self._number_of_guesses,
            "guesses_remaining": self._guesses_remaining,
            "guesses": self._guesses,
            "scores": self._scores,
        }

    def get_answer(self):
        return self._answer

    def get_guesses_remaining(self):
        return self._guesses_remaining

    def guess(self, guess: str):
        if self.get_guesses_remaining() == 0:
            return Score.OUT_OF_GUESSES
        if len(guess) != len(self._answer):
            return Score.INVALID_GUESS
        if guess not in all_valid_words:
            return Score.NOT_A_WORD

        self._guesses_remaining -= 1
        if guess == self._answer:
            return [Score.CORRECT for _ in guess]
        return [
            Score.CORRECT
            if guess_letter == answer_letter
            else (
                Score.WRONG_LOCATION
                if guess_letter in self._answer
                else Score.INCORRECT_LETTER
            )
            for guess_letter, answer_letter in zip(guess, self._answer)
        ]


class GameStatePersister(abc.ABC):
    def save_game(self, uuid: str, state: dict):
        ...

    def load_game(self, uuid: str):
        ...


class JSONFileGameStatePersister(GameStatePersister):
    def __init__(self, filename: str = "game_state.json"):
        self._filename = filename
        # Create the file if it doesn't exist:
        if not os.path.exists(filename):
            with open(filename, "w") as f:
                f.write("{}")

    def _get_contents(self):
        with open(self._filename, "r") as f:
            return json.load(f)

    def save_game(self, uuid: str, state: dict):
        print("Saving game state", uuid, state)
        # Get the current contents:
        games = self._get_contents()
        games[uuid] = state
        # Write the new contents:
        with open(self._filename, "w") as f:
            json.dump(games, f, indent=4)

    def load_game(self, uuid: str):
        print("Loading game state", uuid)
        games = self._get_contents()
        game = games.get(uuid, None)
        if game and game.get("game_status", "None") == "IN_PROGRESS":
            return game


class DynamoDBGameStatePersister(GameStatePersister):
    def __init__(self, dynamodb_table_name: str):
        self._dynamodb_table_name = dynamodb_table_name

        # Check to see if the table exists
        dynamodb = boto3.resource("dynamodb")
        table_exists = False
        try:
            dynamodb.Table(self._dynamodb_table_name).load()
            table_exists = True
        except:
            pass

        if not table_exists:
            self._initialize_database()

    def _initialize_database(self):
        # Initialize the database by creating the table. The table has auto-
        # scaling enabled, so it will automatically scale up and down as
        # needed. (There is no provisioned read/write capacity.)

        # Primary key is "uuid"
        # Sort key is "game_status"

        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.create_table(
            TableName=self._dynamodb_table_name,
            KeySchema=[
                {"AttributeName": "uuid", "KeyType": "HASH"},
                {"AttributeName": "game_status", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "uuid", "AttributeType": "S"},
                {"AttributeName": "game_status", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Wait until the table exists.
        table.meta.client.get_waiter("table_exists").wait(
            TableName=self._dynamodb_table_name
        )

    def save_game(self, uuid: str, state: dict):
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(self._dynamodb_table_name)
        print(state)

        # Get the current contents:
        response = table.get_item(Key={"uuid": uuid, "game_status": "IN_PROGRESS"})
        if "Item" in response:
            # Delete the old item:
            table.delete_item(Key={"uuid": uuid, "game_status": "IN_PROGRESS"})
        # Write the new item:
        table.put_item(
            Item={
                "uuid": uuid,
                "game_status": state.get("game_status", "IN_PROGRESS"),
                "state": json.dumps(state),
            }
        )

    def load_game(self, uuid: str):
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(self._dynamodb_table_name)
        # Only get IN_PROGRESS games:
        response = table.get_item(Key={"uuid": uuid, "game_status": "IN_PROGRESS"})
        if "Item" in response:
            state = response["Item"]["state"]
            print(state)
            return json.loads(state)
        return None


class CustomFlask(Flask):
    jinja_options = Flask.jinja_options.copy()
    jinja_options.update(
        dict(
            block_start_string="<%",
            block_end_string="%>",
            variable_start_string="%%",
            variable_end_string="%%",
            comment_start_string="<#",
            comment_end_string="#>",
        )
    )


# class StatefulGameServer:
#     """
#     This is a flask server that lets a player self-identify and play a game.

#     Each game is associated with a user's unique ID. A user generates a UUID
#     client-side, and the server uses that UUID to identify the game. (This is
#     not a security feature, but it enables us to have authless games without
#     sharing the full state client-side.)

#     The ONLY endpoint a user interacts with is the /game/<uuid> endpoint:
#     POSTS to this endpoint are used to make guesses; the state of the game is
#     returned in the response. The response is JSON, and the format is:

#         {
#             "state": "IN_PROGRESS" | "WON" | "LOST" | "FORFEIT",
#             "guesses_remaining": int,
#             "number_of_guesses": int,
#             "guesses": [str, ...],
#             "scores": [[SCORE], ...]
#         }

#     When a user posts to this endpoint, we look for the first "IN_PROGRESS"
#     game they've created. If there is no such game, we create one.

#     If the game is in progress, we check the guess and return the game state.

#     We do not currently support forfeiting, but this will be a way to let a
#     user give up on a word in the future.

#     DATABASE

#     The database is a DynamoDB table. The table has a single primary key,
#     "uuid", which is the UUID of the game. The table has two attributes:
#     * "game_status": the status of the game, (in progress, etc)
#     * "game_state": the state of the game, encoded as stringified JSON.

#     """

#     def __init__(self, game_state_store_factory: Callable[[], GameStatePersister]):
#         self._app = CustomFlask(__name__)
#         CORS(self._app)
#         self._game_state_store_factory = game_state_store_factory

#         self._app.add_url_rule(
#             "/game/<uuid>",
#             "game",
#             self._game_endpoint,
#             methods=["POST", "GET"],
#         )

#         self._app.add_url_rule("/", "index", self._index_endpoint, methods=["GET"])

#     def _index_endpoint(self):
#         return render_template("index.html")

#     def _game_endpoint(self, uuid: str):
#         # if this is a GET, we just return the game state
#         game_state = self._get_game(uuid)
#         if request.method == "GET":
#             if game_state is None:
#                 return jsonify({"error": "NOT_FOUND"})
#             else:
#                 # If the game is in progress, remove `answer`:
#                 if game_state.get("game_status", None) == "IN_PROGRESS":
#                     game_state["answer"] = None

#                 return jsonify(game_state)

#         # get the guess from the request
#         guess = request.json["guess"]

#         if game_state is None:
#             game_state = self._create_game(uuid)

#         # score the guess
#         print(game_state)
#         game = Game.from_game_state(game_state)
#         score = game.guess(guess)

#         if isinstance(score, str):
#             return jsonify({"error": score})

#         # update the game state
#         game_state["guesses"].append(guess)
#         game_state["scores"].append(score)
#         game_state["guesses_remaining"] -= 1

#         # if you guessed correctly, the game is over
#         if game.get_answer() == guess:
#             game_state["game_status"] = "WON"
#             game_state["guesses_remaining"] = 0
#         # if you guessed incorrectly, and you have no guesses left, the game is over
#         elif game_state["guesses_remaining"] == 0:
#             game_state["game_status"] = "LOST"
#             game_state["guesses_remaining"] = 0
#         # otherwise, the game is still in progress
#         else:
#             game_state["game_status"] = "IN_PROGRESS"

#         # Save the game state to the database
#         self._save_game(uuid, game_state)

#         # Return the game state
#         # If the game is in progress, remove `answer`:
#         if game_state.get("game_status", None) == "IN_PROGRESS":
#             game_state["answer"] = None
#         return jsonify(game_state)

#     def _get_game(self, uuid: str):
#         game_state_store = self._game_state_store_factory()
#         return game_state_store.load_game(uuid)

#     def _create_game(self, uuid: str):
#         # Create a new game
#         game = Game(answer=wordlist.get_random_word(length=5))

#         # Save the game state to the database
#         state = game.to_game_state()
#         self._save_game(uuid, state)

#         return state

#     def _save_game(self, uuid: str, state: dict):
#         game_state_store = self._game_state_store_factory()
#         game_state_store.save_game(uuid, state)

#     def serve(self, debug=False):
#         self._app.run(debug=debug, host="0.0.0.0")

#     def __call__(self, debug=False):
#         self.serve(debug)


# # if __name__ == "__main__":
# stateful_game_server = StatefulGameServer(
#     # lambda: JSONFileGameStatePersister()
#     lambda: DynamoDBGameStatePersister("wordgame-state")
# )
# # stateful_game_server.serve(True)

_game_state_store_factory = lambda: DynamoDBGameStatePersister("wordgame-state")
# _game_state_store_factory = lambda: JSONFileGameStatePersister()

app = CustomFlask(__name__)
CORS(app)


def _index_endpoint():
    return render_template("index.html")


def _get_game(uuid: str):
    game_state_store = _game_state_store_factory()
    return game_state_store.load_game(uuid)


def _save_game(uuid: str, state: dict):
    game_state_store = _game_state_store_factory()
    game_state_store.save_game(uuid, state)


def _create_game(uuid: str):
    # Create a new game
    game = Game(answer=wordlist.get_random_word(length=5))

    # Save the game state to the database
    state = game.to_game_state()
    _save_game(uuid, state)

    return state


def _game_endpoint(uuid: str):
    # if this is a GET, we just return the game state
    game_state = _get_game(uuid)
    if request.method == "GET":
        if game_state is None:
            return jsonify({"error": "NOT_FOUND"})
        else:
            # If the game is in progress, remove `answer`:
            if game_state.get("game_status", None) == "IN_PROGRESS":
                game_state["answer"] = None

            return jsonify(game_state)

    # get the guess from the request
    guess = request.json["guess"]

    if game_state is None:
        game_state = _create_game(uuid)

    # score the guess
    print(game_state)
    game = Game.from_game_state(game_state)
    score = game.guess(guess)

    if isinstance(score, str):
        return jsonify({"error": score})

    # update the game state
    game_state["guesses"].append(guess)
    game_state["scores"].append(score)
    game_state["guesses_remaining"] -= 1

    # if you guessed correctly, the game is over
    if game.get_answer() == guess:
        game_state["game_status"] = "WON"
        game_state["guesses_remaining"] = 0
    # if you guessed incorrectly, and you have no guesses left, the game is over
    elif game_state["guesses_remaining"] == 0:
        game_state["game_status"] = "LOST"
        game_state["guesses_remaining"] = 0
    # otherwise, the game is still in progress
    else:
        game_state["game_status"] = "IN_PROGRESS"

    # Save the game state to the database
    _save_game(uuid, game_state)

    # Return the game state
    # If the game is in progress, remove `answer`:
    if game_state.get("game_status", None) == "IN_PROGRESS":
        game_state["answer"] = None
    return jsonify(game_state)


app.add_url_rule(
    "/game/<uuid>",
    "game",
    _game_endpoint,
    methods=["POST", "GET"],
)

app.add_url_rule("/", "index", _index_endpoint, methods=["GET"])
