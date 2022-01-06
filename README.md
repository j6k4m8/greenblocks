# manygreenblocks

a wordle clone, for when you NEED to have another wordle NOW

<img width="654" alt="image" src="https://user-images.githubusercontent.com/693511/148328314-bbbec492-6e79-420d-b268-3762dda593f3.png">

The list of common words in `common5.txt` was derived from [this page](https://raw.githubusercontent.com/first20hours/google-10000-english/master/google-10000-english-usa-no-swears-short.txt), filtering on five-letter words.

The complete wordlist was generated using:

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
