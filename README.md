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
