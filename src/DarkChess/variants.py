import chess
from math import inf
from warnings import warn as _warn

def _quantify(iterable, pred=bool):
	return sum(map(pred, iterable))

def monkey_polyfill(chess):
	if not hasattr(chess, 'NO_PIECE'):
		chess.NO_PIECE = -len(chess.PIECE_NAMES)
	if not hasattr(chess, 'UNBLOCKABLE_PIECES'):
		chess.UNBLOCKABLE_PIECES = {chess.KNIGHT}
	if not hasattr(chess, 'BB_PAWN_RANK'):
		chess.BB_PAWN_RANK = [chess.BB_RANK_7, chess.BB_RANK_2]
	if not hasattr(chess.Move, 'remove'):
		@classmethod
		def _move_remove(cls, square, **kwargs):
			return cls(square, square, drop=chess.NO_PIECE, **kwargs)
		chess.Move.remove = _move_remove
		@classmethod
		def _move_from_uci(cls, uci):
			if uci == "0000":
				# Null move
				return cls.null()
			elif (len(uci) == 4 or (4 <= len(uci) <= 5 and uci[0].lower() == "x")) and "@" == uci[1]:
				# Drop move, may or may not be an anonymous capture
				drop = chess.PIECE_SYMBOLS.index(uci[0].lower()) if uci[0].lower() != "x" else chess.NO_PIECE
				if len(uci) == 5:
					promotion = chess.PIECE_SYMBOLS.index(uci[4]) if uci[4].lower() != "x" else chess.NO_PIECE
				else:
					promotion = None
				square = chess.SQUARE_NAMES.index(uci[2:4])
				return cls(square, square, promotion=promotion, drop=drop)
			elif 4 <= len(uci) <= 5:
				# Normal move, may or may not be a promotion
				from_square = chess.SQUARE_NAMES.index(uci[0:2])
				to_square = chess.SQUARE_NAMES.index(uci[2:4])
				if len(uci) == 5:
					promotion = chess.PIECE_SYMBOLS.index(uci[4]) if uci[4].lower() != "x" else chess.NO_PIECE
				else:
					promotion = None
				if from_square == to_square:
					raise ValueError(f"invalid uci (use 0000 for null moves): {uci!r}")
				return cls(from_square, to_square, promotion=promotion)
			else:
				raise ValueError(f"expected uci string to be of length 4 or 5: {uci!r}")
		chess.Move.from_uci = _move_from_uci
		def _move_uci(self):
			if self.drop:
				if self.drop == chess.NO_PIECE:
					return chess.piece_symbol(self.drop) + "@" + chess.SQUARE_NAMES[self.to_square] + (chess.piece_symbol(self.promotion) if self.promotion else "")
				else:
					return chess.piece_symbol(self.drop).upper() + "@" + chess.SQUARE_NAMES[self.to_square]
			elif self.promotion:
				return chess.SQUARE_NAMES[self.from_square] + chess.SQUARE_NAMES[self.to_square] + chess.piece_symbol(self.promotion)
			elif self:
				return chess.SQUARE_NAMES[self.from_square] + chess.SQUARE_NAMES[self.to_square]
			else:
				return "0000"
		chess.Move.uci = _move_uci
	try:
		if chess.piece_symbol(chess.NO_PIECE) is None:
			raise ValueError
	except (IndexError, ValueError):
		def _piece_symbol(piece_type):
			return chess.typing.cast(str, chess.PIECE_SYMBOLS[piece_type] if piece_type != chess.NO_PIECE else "x")
		chess.piece_symbol = _piece_symbol
	if True:
		def _piece_symbol(self):
			symbol = chess.piece_symbol(self.piece_type)
			return symbol.upper() if self.color and self.piece_type != chess.NO_PIECE else symbol
		chess.Piece.symbol = _piece_symbol
	if not hasattr(chess.Piece, '__invert__'):
		def _piece_invert(self):
			return type(self)(self.piece_type, not self.color)
		chess.Piece.__invert__ = _piece_invert

class DarkBoard(chess.Board):
	def remove_piece_at(self, square, discreetly=False):
		if discreetly and type(super()) is chess.Board:
			return chess.BaseBoard.remove_piece_at(self, square)
		else:
			return super().remove_piece_at(square)
	def set_piece_at(self, square, piece, discreetly=False):
		if discreetly and type(super()) is chess.Board:
			return chess.BaseBoard.set_piece_at(self, square, piece)
		else:
			return super().set_piece_at(square, piece)
	def get_view(self, color):
		if self.fullmove_number != 1:
			raise NotImplementedError("TODO")
		if isinstance(self, DarkBoardView):
			raise NotImplementedError
		return DarkBoardView(self, pov=color)

class DarkBoardView(DarkBoard):
	monkey_polyfill(chess)
	def __init__(self, board, *args, pov=None, **kwargs):
		if pov is None:
			raise NotImplementedError
		super().__init__(*args, **kwargs)
		board._board_state().restore(self)
		self.pov = pov
		self.forget_player(not self.pov)
		self.vision = self.calc_vision()
		self.esp_action = chess.SquareSet()
		self.esp_piece = chess.SquareSet()
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
				self.remove_piece_at(square, discreetly=True)
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
			# Square in front:
			bonus_vision.add(chess.square(chess.square_file(square), chess.square_rank(square) + [-1, 1][piece.color]))
			# 2-move:
			if square in chess.SquareSet(chess.BB_PAWN_RANK[piece.color]):
				# Pawn is on its rank, assuming it hasn't moved yet
				bonus_vision.add(chess.square(chess.square_file(square), chess.square_rank(square) + [-2, 2][piece.color]))
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
					if square_index in self.esp_action:
						builder.append(action_square)
					elif square_index in self.vision:
						builder.append(empty_square)
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
				if square in self.esp_action:
					builder.append("!")
				elif square in self.vision:
					builder.append(".")
				elif square in self.esp_piece:
					builder.append("*")
				else:
					builder.append("?")
			if chess.BB_SQUARES[square] & chess.BB_FILE_H:
				if square != chess.H1:
					builder.append("\n")
			else:
				builder.append(" ")
		return "".join(builder)
