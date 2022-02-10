import chess
from rng import RijndaelRng
import zmq
import logging
logging.basicConfig(level=logging.INFO)

def _main(my_color=chess.WHITE):
	board = chess.Board()
	board.forget_pieces(lambda square: board.color_at(square) != my_color)
	global _opponent
	_opponent = chess.BaseBoard()
	_opponent.forget_pieces(lambda square: board.color_at(square) == my_color)
	board.remove_piece_at(chess.D2)
	board.remove_piece_at(chess.E2)
	visibility_generator = gain_vision(board, my_color)
	visibility = next(visibility_generator)
	while True:
		try:
			new_pieces = _query_opponent(visibility, not my_color)
			visibility = visibility_generator.send(new_pieces)
		except StopIteration:
			break
	#print(visibility)
	print(board.unicode_fog(visibility))

def gain_vision(board, color, *, runs=range(1, 8), **kwargs):
	for i in runs:
		new_pieces = (yield _calc_visibility(board, color, vision_limit=i, **kwargs))
		for square, piece in new_pieces.items():
			board.set_piece_at(square, piece)

def _calc_visibility(board, color, vision_limit=99, self_vision=False):
	visibility = chess.SquareSet(chess.BB_EMPTY)
	for square in chess.SQUARES:
		if self_vision:
			if board.color_at(square) == color:
				visibility.add(square)
				continue
		for spotter_square in board.attackers(color, square):
			spotter = board.piece_at(spotter_square)
			if spotter.piece_type in chess.UNBLOCKABLE_PIECES or \
			   chess.square_distance(spotter_square, square) <= vision_limit:
				visibility.add(square)
	return visibility


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
	logging.info("Sending list of seen tiles")
	socket.send_json(list(squares))
	logging.info("List of seen tiles sent")
	logging.info("Receiving vision from seen tiles")
	new_pieces = socket.recv_json()
	logging.info("Vision from seen tiles received")
	new_pieces = dict(((square, chess.Piece.from_symbol(symbol)) for square, symbol in new_pieces.items()))
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
	logging.info("List of seen tiles received")
	visible_pieces = board.piece_map(mask=int(squares))
	logging.info("Sending vision for seen tiles")
	socket.send_json(dict((square,TODO) for TODO in TODO))
	logging.info("Vision for seen tiles sent")
	return squares


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
	import sys
	sys.exit(_main())
