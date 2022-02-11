import chess
from rng import RijndaelRng
import zmq
import logging
import time
from sys import stdout
logging.basicConfig(level=logging.INFO, stream=stdout)

def _main(my_color=chess.WHITE):
	global white_view
	global black_view
	white_view = chess.Board()
	white_view.forget_pieces(lambda square: white_view.color_at(square) != chess.WHITE)
	black_view = chess.BaseBoard()
	black_view.forget_pieces(lambda square: black_view.color_at(square) != chess.BLACK)
	# White starts out with two pieces missing for debugging
	white_view.remove_piece_at(chess.D2)
	white_view.remove_piece_at(chess.E2)
	if my_color == chess.WHITE:
		visibility = gain_vision(white_view, my_color)
		print(white_view.unicode_fog(visibility))
	else:
		while True: _get_queried(black_view, chess.BLACK)

def _calc_visibility(board, pov_color, vision_limit=99, self_vision=False):
	visibility = chess.SquareSet(chess.BB_EMPTY)
	for square in chess.SQUARES:
		if self_vision:
			if board.color_at(square) == pov_color:
				# Exit early: we can see squares our own pieces are on
				visibility.add(square)
				continue
		for spotter_square in board.attackers(pov_color, square):
			# For each of our pieces that might be attacking this square...
			spotter = board.piece_at(spotter_square)
			if spotter.piece_type not in chess.UNBLOCKABLE_PIECES:
				# (and we are certain isn't being blocked)
				if chess.square_distance(spotter_square, square) > vision_limit:
					continue
			#...count the square as visible
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
	logging.info("Creating context")
	ctx = zmq.Context()
	logging.info("Context created")
	logging.info("Creating socket")
	socket = ctx.socket(zmq.PAIR)
	logging.info("Socket created")
	logging.info("Connecting to socket")
	socket.connect('tcp://localhost:%i' % (64355 + color))
	logging.info("Connected to socket")
	logging.info("Sending list of seen tiles %s", str(squares))
	socket.send_json(_pickle_squareset(squares))
	logging.info("List of seen tiles sent")
	logging.info("Receiving vision from seen tiles")
	new_pieces = _unpickle_piecemap(socket.recv_json())
	logging.info("Vision from seen tiles received %s", str(new_pieces))
	return new_pieces


def _get_queried(board, color):
	logging.info("Creating context")
	ctx = zmq.Context()
	logging.info("Context created")
	logging.info("Creating socket")
	socket = ctx.socket(zmq.PAIR)
	logging.info("Socket created")
	logging.info("Binding to socket")
	socket.bind('tcp://*:%i' % (64355 + color))
	logging.info("Socket bound")
	logging.info("Receiving list of seen tiles")
	squares = chess.SquareSet(socket.recv_json())
	logging.info("List of seen tiles received %s", str(squares))
	visible_pieces = board.piece_map(mask=int(squares))
	logging.info("Sending vision for seen tiles %s", str(visible_pieces))
	socket.send_json(_pickle_piecemap(visible_pieces))
	logging.info("Vision for seen tiles sent")
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
		print("STARTING ROUND %i" % (i + 1))
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
