An implementation of [mental poker](https://people.csail.mit.edu/rivest/pubs/SRA81.pdf) for [dark chess](https://www.chessvariants.com/incinf.dir/darkness.html)

Can two players play mental chess such that:

a. Each player can only see squares that their own pieces are attacking

b. A player who "cheats" and violates (a) by peeking cannot plausibly "get away with it"

c. There is no [3rd-party "referee"](http://www.gamerz.net/pbmserv/darkchess.html) available to keep track of each player's moves

```shell
sudo apt install python3-venv # might be needed
python3 -m venv env/
# bash
. env/bin/activate
pip install -r requirements.txt
cd src/
chesscolor=black python main.py &
chesscolor=white python main.py
```
