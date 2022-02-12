An implementation of [mental poker](https://people.csail.mit.edu/rivest/pubs/SRA81.pdf) for [dark chess](https://www.chessvariants.com/incinf.dir/darkness.html)

-----

# Q

Can two players play the following variant of [correspondence chess](https://en.wikipedia.org/wiki/Correspondence_chess?oldid=5673559):

a. Each player can only "see" squares that their own pieces are attacking

b. A player who cheats and violates (a) by "peeking" cannot plausibly get away with it: he will at least be exposed by the end of the game

c. Neither player trusts any ["referee"](http://www.gamerz.net/pbmserv/darkchess.html) to *confidentially* administer the boardstate (though a loose-lipped-but-honest referee may still be got to adjudicate outcomes, especially after the match)

# A

I believe this is possible, and I will implement an example program to demonstrate it.

# Usage

```shell
# Linux
sudo apt install python3-venv # might be needed
python3 -m venv env/
. env/bin/activate
pip install -r requirements.txt

cd src
chesscolor=white python main.py
## DO THE SAME IN ANOTHER WINDOW: ##
. env/bin/activate
cd src
chesscolor=black python main.py
```

```cmd
REM windows

cd src
set chesscolor=white
python main.py
REM DO THE SAME IN ANOTHER WINDOW-
cd src
set chesscolor=black
python main.py
```

Also pass env `lol=555` if you want White to start out with the D and E pawns removed
