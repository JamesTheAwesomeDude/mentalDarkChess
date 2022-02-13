import chess
from math import inf
from warnings import warn as _warn

def _quantify(iterable, pred=bool):
	return sum(map(pred, iterable))

@classmethod
def _move_remove(cls, square):
	return cls(square, square, drop=chess.NO_PIECE)

def _piece_invert(self):
	return type(self)(self.piece_type, not self.color)


def monkey_patch(chess):
	chess.NO_PIECE = -len(chess.PIECE_NAMES)
	chess.NO_SQUARE = len(chess.SQUARES)
	chess.UNBLOCKABLE_PIECES = {chess.KNIGHT}
	chess.Move.remove = _move_remove
	chess.Piece.__invert__ = _piece_invert

class DarkBoard(chess.Board):
	monkey_patch(chess)
	def __init__(self, *args, pov=None, **kwargs):
		if pov is None:
			_warn(NotImplementedError)
		super().__init__(*args, **kwargs)
		self.pov = pov
		self.forget_player(not self.pov)
		self.vision = self.calc_vision()
		self.esp_action = chess.SquareSet()
		self.esp_piece = chess.SquareSet()
	def remove_piece_at(self, square, gently=False):
		if gently and type(super()) is chess.Board:
			return chess.BaseBoard.remove_piece_at(self, square)
		else:
			return super().remove_piece_at(square)
	def set_piece_at(self, square, piece, gently=False):
		if gently and type(super()) is chess.Board:
			return chess.BaseBoard.set_piece_at(self, square, piece)
		else:
			return super().set_piece_at(square, piece)
	def forget_player(self, color=None):
		if color is None:
			_warn("Guessing which side to forget")
			if _quantify(chess.COLORS, lambda color: bool(self.pieces(chess.KING, color))) == 1:
				# if EXACTLY ONE SIDE has a king, forget the other side's pieces
				color = next(color for color in chess.COLORS if not self.king(color))
			else:
				raise ValueError("Ambiguous color to remove. Not proceeding!")
		for square in chess.SQUARES:
			piece = self.piece_at(square)
			if piece and piece.color == color:
				self.remove_piece_at(square, gently=True)
	def calc_vision(self, *, pov=None, initial=chess.BB_EMPTY, max_vision=inf, self_vision=False):
		vision = chess.SquareSet(initial)
		if pov is None:
			pov = self.pov
		elif self.king(pov) is None:
			_warn("Trying to calculate vision for a side with no king")
		for square in chess.SQUARES:
			piece = self.piece_at(square)
			if not piece:
				# Nobody here, nothing to do.
				# (This loop uses Board.attacks, not Board.attackers)
				continue
			if piece.color != pov:
				# We know there's an enemy piece here,
				# Therefore, we deduce we can see this square
				vision.add(square)
				continue
			elif self_vision:
				# We know there's an allied piece here,
				# but may or may not want to account it
				vision.add(square)
			for dest in (self.attacks(square) | self._bonus_vision(square)):
				# For each maybe-unseen square our piece is attacking:
				# if it's closer than the vision limit,
				if max_vision >= chess.square_distance(square, dest) or (piece.piece_type in chess.UNBLOCKABLE_PIECES and max_vision > 0):
					# then we do, in fact, see it.
					vision.add(dest)
		return vision
	def _bonus_vision(self, square):
		piece = self.piece_at(square)
		if piece is None:
			return chess.SquareSet(chess.BB_EMPTY)
		bonus_vision = chess.SquareSet()
		if piece.piece_type == chess.PAWN:
			bonus_vision.add(chess.square(chess.square_file(square), chess.square_rank(square) + [-1, 1][piece.color]))
		return bonus_vision
	def __repr__(self):
		# TODO: modify board_fen to include fog
		return f"{type(self).__name__}({self.board_fen()!r}, pov={self.pov})"
	def unicode(self, *,
	  invert_color=False,
	  borders=False,
	  empty_square="\u2b58", # HEAVY CIRCLE
	  hidden_square="\u2047", # DOUBLE QUESTION MARK
	  action_square="\u2b57", # HEAVY CIRCLE WITH CIRCLE INSIDE
	  something_square="\u2b59" # HEAVY CIRCLED SALTIRE
	):
		builder = []
		for rank_index in range(7, -1, -1):
			if borders:
				builder.append("  ")
				builder.append("-" * 17)
				builder.append("\n")
				builder.append(RANK_NAMES[rank_index])
				builder.append(" ")
			for file_index in range(8):
				square_index = chess.square(file_index, rank_index)
				if borders:
					builder.append("|")
				elif file_index > 0:
					builder.append(" ")
				piece = self.piece_at(square_index)
				if piece:
					builder.append(piece.unicode_symbol(invert_color=invert_color))
				else:
					if square_index in self.vision:
						builder.append(empty_square)
					elif square_index in self.esp_action:
						builder.append(action_square)
					elif square_index in self.esp_piece:
						builder.append(something_square)
					else:
						builder.append(hidden_square)
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
	def __str__(self):
		builder = []
		for square in chess.SQUARES_180:
			piece = self.piece_at(square)
			if piece:
				builder.append(piece.symbol())
			else:
				if square in self.vision:
					builder.append(".")
				elif square in self.esp_action:
					builder.append(",")
				elif square in self.esp_piece:
					builder.append("!")
				else:
					builder.append("?")
			if chess.BB_SQUARES[square] & chess.BB_FILE_H:
				if square != chess.H1:
					builder.append("\n")
			else:
				builder.append(" ")
		return "".join(builder)
