import chess
from rng import RijndaelRng
import zmq
import logging
import time
from sys import stdout
logging.basicConfig(level=logging.INFO, stream=stdout)

def _main(my_color=chess.WHITE):
	global board
	board = chess.Board()
	board.forget_pieces(lambda square: board.color_at(square) != my_color)
	# White starts out with two pieces missing for debugging
	if my_color == chess.WHITE:
		board.remove_piece_at(chess.D2)
		board.remove_piece_at(chess.E2)
	if my_color == chess.BLACK:
		their_turn()
	while True:
		if my_turn():
			return "VICTORY"
		if their_turn():
			return "FAT LOSS"

def my_turn(board, my_color):
	visibility = gain_vision(board, my_color)
	print(board.unicode_fog(visibility))
	move = chess.Move.from_uci(input("YUOR MOEV (in UCI FORMAT such as e2e4)\n> "))
	target = board.piece_at(move.to_square)
	assert target is None or target.color != my_color
	board.push(move)
	if target and target.piece_type == chess.KING:
		return True
	print(board.unicode_fog(visibility))

def their_turn():
	while True: _get_queried(black_view, chess.BLACK)


def _is_visible(board, square, pov_color, vision_limit=99, self_vision=False):
	if board.color_at(square) == pov_color:
		# We have a square on this piece; exit early
		return self_vision
	for spotter_square in board.attackers(pov_color, square):
		spotter = board.piece_at(spotter_square)
		if spotter.piece_type not in chess.UNBLOCKABLE_PIECES or vision_limit < 1:
			# Piece may be vision encumbered
			if chess.square_distance(spotter_square, square) <= vision_limit:
				# It could, in fact, see the distance
				return True
			else:
				# Theoretically spotted, but outside of range
				# skip this spotter and try the next
				continue
		else:
			# Knight with vision >= 1 -- unencumbrable
			return True
	# All candidate spotters -- if there were any -- were disqualified
	# Square is clearly not visible with current boardstate and vision
	return False

def _calc_visibility(board, pov_color, vision_limit=99, self_vision=False):
	visibility = chess.SquareSet(chess.BB_EMPTY)
	for square in chess.SQUARES:
		if _is_visible(board, square, pov_color, vision_limit, self_vision):
			visibility.add(square)
	return visibility


def _pickle_piecemap(piecemap):
	return dict(((square, piece.symbol()) for square, piece in piecemap.items()))

def _unpickle_piecemap(dict_piecemap):
	return dict(((int(square), chess.Piece.from_symbol(symbol)) for square, symbol in dict_piecemap.items()))

def _pickle_squareset(squareset):
	return list(squareset)

def _unpickle_squareset(list_squareset):
	return chess.SquareSet(list_squareset)


def _query_opponent(squares, color):
	ctx = zmq.Context()
	
	socket = ctx.socket(zmq.PAIR)
	socket.connect('tcp://localhost:%i' % (64355 + color))
	socket.send_json(_pickle_squareset(squares))
	new_pieces = _unpickle_piecemap(socket.recv_json())
	return new_pieces


def _get_queried(board, color):
	ctx = zmq.Context()
	socket = ctx.socket(zmq.PAIR)
	socket.bind('tcp://*:%i' % (64355 + color))
	previous_squares = None
	squares = chess.SquareSet(socket.recv_json())
	while squares != previous_squares:
		visible_pieces = board.piece_map(mask=int(squares))
		socket.send_json(_pickle_piecemap(visible_pieces))
		squares, previous_squares = chess.SquareSet(socket.recv_json()), squares
	return squares


def gain_vision(board, self_color, *, queryfunc=_query_opponent, runs=range(1, 8), **kwargs):
	visibility_generator = _gain_vision(board, self_color, runs=runs, **kwargs)
	visibility = next(visibility_generator)
	while True:
		try:
			new_pieces = queryfunc(visibility, not self_color)
			visibility = visibility_generator.send(new_pieces)
		except StopIteration:
			break
	return visibility

def _gain_vision(board, self_color, *, runs=range(1, 8), **kwargs):
	for i in runs:
		print("STARTING ROUND %i" % i)
		new_pieces = (yield _calc_visibility(board, self_color, vision_limit=i, **kwargs))
		time.sleep(1)
		for square, piece in new_pieces.items():
			print("ADDING PIECE %s AT %s" % (repr(piece), repr(square)))
			board.set_piece_at(square, piece)

#def _query_opponent(squares):
#	global _opponent
#	new_pieces = dict()
#	for square in squares:
#		new_piece = _opponent.piece_at(square)
#		if new_piece is not None:
#			new_pieces[square] = new_piece
#	return new_pieces


chess.UNBLOCKABLE_PIECES = {chess.KNIGHT}

# TODO: class DarkBoard(BaseBoard)

def _forget_pieces(board, predicate):
	for square in filter(predicate, chess.SQUARES):
		board.remove_piece_at(square)

chess.BaseBoard.forget_pieces = _forget_pieces

def _str_fog(board, visibility, hidden_symbol="?"):
	builder = []
	visibility = chess.SquareSet(visibility)
	for square in chess.SQUARES_180:
		piece = board.piece_at(square)
		if piece:
			builder.append(piece.symbol())
		else:
			builder.append("." if (square in visibility) else hidden_symbol)
		if chess.BB_SQUARES[square] & chess.BB_FILE_H:
			if square != chess.H1:
				builder.append("\n")
		else:
			builder.append(" ")
	return "".join(builder)

chess.BaseBoard.str_fog = _str_fog

def _unicode_fog(board, visibility, *, hidden_square="\u2047", invert_color=False, borders=False, empty_square="\u2B58"):
	builder = []
	visibility = chess.SquareSet(visibility)
	for rank_index in range(7, -1, -1):
		if borders:
			builder.append("  ")
			builder.append("-" * 17)
			builder.append("\n")
			builder.append(RANK_NAMES[rank_index])
			builder.append(" ")
		for file_index in range(8):
			square = chess.square(file_index, rank_index)
			if borders:
				builder.append("|")
			elif file_index > 0:
				builder.append(" ")
			piece = board.piece_at(square)
			if piece:
				builder.append(piece.unicode_symbol(invert_color=invert_color))
			else:
				builder.append(empty_square if (square in visibility) else hidden_square)
		if borders:
			builder.append("|")
		if borders or rank_index > 0:
			builder.append("\n")
	if borders:
		builder.append("  ")
		builder.append("-" * 17)
		builder.append("\n")
		builder.append("   a b c d e f g h")
	return "".join(builder)

chess.BaseBoard.unicode_fog = _unicode_fog

if __name__ == '__main__':
	import sys, os
	color = {"white": chess.WHITE, "black": chess.BLACK}[os.environ.get("chesscolor", "white")]
	sys.exit(_main(color))
