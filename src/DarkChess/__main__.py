from sys import stdout
from os import urandom, environ
from warnings import warn

import chess
import zmq
from zmq.utils.z85 import encode as z85encode, decode as z85decode
import logging
logging.basicConfig(stream=stdout, level=getattr(logging, environ.get('LOGLEVEL', 'INFO')))

from .variants import DarkBoard
from ._protos import Conversation, CHESS_PORT


_UNICODE_TERMINAL = ('UTF-' in environ.get('LANG', 'C'))


def show_board(board, *args, **kwargs):
	if _UNICODE_TERMINAL:
		print(board.unicode(*args, **kwargs))
	else:
		if(args or kwargs):
			warn("Arguments to show_board not supported in this environment (LANG=%s)" % environ.get('LANG', ''))
		print(str(board))


def _main(board, color, addr=None):
	winner = None
	conv = Conversation(color, addr)
	if color == chess.BLACK:
		winner = their_turn(conv, board)
	while winner is None:
		if board.turn == color:
			winner = my_turn(conv, board)
		else:
			winner = their_turn(conv, board)
	if winner == color:
		print("WINNER IS YOU")
	else:
		print("L O S S")
	return 0


def my_turn(conv, board):
	board.forget_player(not board.turn)
	alice = conv.probe_opponent(board)
	revealed = next(alice)
	logging.info('REVEALED: %s', ','.join('%s@%s' % (piece.symbol(), chess.SQUARE_NAMES[square]) for square, piece in revealed.items() if piece))
	board.vision = board.calc_vision()
	show_board(board)
	move = chess.Move.from_uci(input('MOVE IN UCI FORMAT (e.g. e2e4,f7f5)\n> '))
	dest = move.to_square
	captured_piece = board.piece_at(dest)
	if captured_piece is None:
		alice.send(chess.NO_SQUARE)
	elif captured_piece.color == board.turn:
		raise ValueError("Can't capture your own %s piece %s@%s")
	else:
		logging.info("CAPTURED: %s@%s", captured_piece.symbol(), chess.SQUARE_NAMES[dest])
		alice.send(dest)
	board.push(move)
	if captured_piece and captured_piece.piece_type == chess.KING:
		return not board.turn
	board.forget_player(board.turn)
	alice = conv.probe_opponent(board)
	revealed = next(alice)
	logging.info('REVEALED: %s', ','.join('%s@%s' % (piece.symbol(), chess.SQUARE_NAMES[square]) for square, piece in revealed.items() if piece))
	alice.send(chess.NO_SQUARE)
	board.vision = board.calc_vision()
	show_board(board)


def their_turn(conv, board):
	board.forget_player(board.turn)
	bob = conv.respond_to_probe(board)
	queries = next(bob)
	captured_square = next(bob)
	if captured_square == chess.NO_SQUARE:
		captured_piece = None
		logging.info("NO CAPTURE BY OPPONENT THIS TURN")
		board.push(chess.Move.null())
	else:
		captured_piece = board.piece_at(captured_square)
		logging.info("OPPONENT CAPTURED: %s@%s", captured_piece.symbol(), chess.SQUARE_NAMES[captured_square])
		board.push(chess.Move.remove(captured_square))
	if captured_piece and captured_piece.piece_type == chess.KING:
		return not board.turn
	board.forget_player(not board.turn)
	bob = conv.respond_to_probe(board)
	queries = next(bob)
	next(bob)

def __entrypoint__():
	import sys
	colorstring = environ.get('chesscolor', None)
	if colorstring is None:
		colorstring = {'W': 'white', 'B': 'black'}[input("Do you want to play as WHITE (w) or as BLACK (b)?\n> ")[0].upper()]
	color = chess.COLOR_NAMES.index(colorstring)
	if color != chess.WHITE:
		addr = input(f"What PC is White on? [tcp://127.0.0.1:{CHESS_PORT}]\n> ") or None
	else:
		addr = None
	board = DarkBoard(pov=color)
	if "lol" in environ:
		board.remove_piece_at(chess.D2)
		board.remove_piece_at(chess.E2)
	sys.exit(_main(board, color))

if __name__ == '__main__':
	__entrypoint__()
