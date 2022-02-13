from math import inf
import inspect, ast, re
from warnings import warn

def _quantify(iterable, pred=bool):
	return sum(map(pred, iterable))

def monkey_patch(chess):
	chess.NO_PIECE = -len(chess.PIECE_NAMES)
	chess.NO_SQUARE = len(chess.SQUARES)
	chess.UNBLOCKABLE_PIECES = {chess.KNIGHT}
	@classmethod
	def _move_remove(cls, square):
		return cls(square, square, drop=chess.NO_PIECE)
	chess.Move.remove = _move_remove
	def _piece_invert(self):
		return type(self)(self.piece_type, not self.color)
	chess.Piece.__invert__ = _piece_invert
	class DarkBoard(chess.Board):
		#def __init__(self, *args, **kwargs):
		#	super().__init__(*args, **kwargs)
		#	self.vision = chess.SquareSet(chess.SQUARES)
		@property
		def vision(self):
			return self.calc_vision()
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
				warn("Guessing which side to forget")
				if _quantify(chess.COLORS, lambda color: bool(self.pieces(chess.KING, color))) == 1:
					# if EXACTLY ONE SIDE has a king, forget the other side's pieces
					color = next(color for color in chess.COLORS if not self.king(color))
				else:
					raise ValueError("Ambiguous color to remove. Not proceeding!")
			for square in chess.SQUARES:
				piece = self.piece_at(square)
				if piece and piece.color == color:
					self.remove_piece_at(square, gently=True)
		def check_vision(self, square, color=None, max_vision=inf):
			if color is None:
				color = self.turn
			if self.king(self.turn) is None:
				warn("Trying to calculate vision for a side with no king")
			for attacker_square in self.attackers(self.turn, square):
				attacker = self.piece_at(attacker_square)
				if attacker.piece_type not in chess.UNBLOCKABLE_PIECES or max_vision < 1:
					if chess.square_distance(attacker_square, square) <= max_vision:
						return True
		def calc_vision(self, initial_vision=chess.BB_EMPTY, max_vision=inf, self_vision=False):
			vision = chess.SquareSet(initial_vision)
			for square in chess.SQUARES:
				if square in vision:
					continue
				piece = self.piece_at(square)
				if piece:
					if self_vision or piece.color != self.turn:
						vision.add(square)
				if self.check_vision(square, max_vision):
					vision.add(square)
			return vision
		def unicode(self, *, invert_color: bool = False, borders: bool = False, empty_square: str = "\u2b58", hidden_square: str = "\u2047") -> str:
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
						builder.append(empty_square if square_index in self.vision else hidden_square)
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
		def __str__(self) -> str:
			builder = []
			vision = self.calc_vision()
			for square in chess.SQUARES_180:
				piece = self.piece_at(square)
				if piece:
					builder.append(piece.symbol())
				else:
					builder.append("." if square in vision else "?")
				if chess.BB_SQUARES[square] & chess.BB_FILE_H:
					if square != chess.H1:
						builder.append("\n")
				else:
					builder.append(" ")
			return "".join(builder)
	chess.DarkBoard = DarkBoard
