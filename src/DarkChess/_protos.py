import logging
import chess
import zmq
from os import urandom
import socket
from itertools import islice
from collections import deque
#logging.basicConfig(stream=stdout, level=getattr(logging, environ.get('LOGLEVEL', 'INFO')))
import bencodepy

from ._crypto import h, gen_fake_pubkeys, make_real_keypair, publickey, pk_encrypt, pk_decrypt, prettyprint_bytes


CHESS_PORT = 64355


class Conversation():
	def __init__(self, color, addr=None):
		self._color = color
		self._ctx = zmq.Context()
		self._socket = self._ctx.socket(zmq.PAIR)
		if color == chess.WHITE:
			if addr is None:
				# Listen on all interfaces by default
				addr = 'tcp://*:%u' % CHESS_PORT
				# If doing so, inform the user of
				# the available interfaces for their convenience
				for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
					print("Listening on: %s" % addr.replace('//*', f'//{ip}', 1))
			self._socket.bind(addr)
		elif color == chess.BLACK:
			if addr is None:
				# Connect to localhost by default
				addr = 'tcp://127.0.0.1:%u' % CHESS_PORT
			self._socket.connect(addr)
		else:
			raise ValueError(color)
	def alice_seed(self, turn=None):
		# Commit to a seed value which
		# we will use to deterministically
		# generate random fake publickeys
		# so Bob can verify after the match
		# that we were unable to decrypt
		# squares we weren't entitled to see
		a = urandom(16)
		logging.info('CHOSE SEED HEAD: %s', prettyprint_bytes(a))
		ha = h(a)
		logging.info('SEED HEAD COMMITMENT #%s: %s', str(turn) if turn is not None else '?', prettyprint_bytes(ha))
		self._send_seed_head_commitment(ha)
		b = self._recv_seed_tail()
		logging.info('GOT SEED TAIL: %s', prettyprint_bytes(b))
		seed = h(a + b)
		logging.info('SEED: %s', prettyprint_bytes(seed))
		return seed
	def bob_seed(self, turn=None):
		b = urandom(16)
		logging.info('CHOSE SEED TAIL: %s', prettyprint_bytes(b))
		self._send_seed_tail(b)
		ha = self._recv_seed_head_commitment()
		logging.info('GOT SEED HEAD COMMITMENT #%s: %s', str(turn) if turn is not None else '?', prettyprint_bytes(ha))
		return b, ha
	def _send_seed_tail(self, b):
		self._socket.send_serialized(b, _serialize)
	def _recv_seed_tail(self):
		b = self._socket.recv_serialized(_deserialize)
		return b
	def _send_seed_head_commitment(self, hseed):
		self._socket.send_serialized(hseed, _serialize)
	def _recv_seed_head_commitment(self):
		hseed = self._socket.recv_serialized(_deserialize)
		return hseed
	def peek_opponents_pieces(self, board, seed, j=0):
		fake_pk_gen = gen_fake_pubkeys(seed)
		consume(fake_pk_gen, j * len(chess.SQUARES))
		# Accumulate all the pieces we see
		# during this round of peeking,
		# which starts with a blank slate:
		board.forget_player(not self._color)
		board.vision = chess.SquareSet()
		piece_map = dict()
		# Minimum vision 1; maximum 7:
		# since the furthest any piece can
		# see is 7 pieces (across the board,
		# less its own square), and there's
		# no reason to send a query for
		# vision zero
		# (This must be done incrementally
		# because, say, a piece 3 units away
		# may block our vision of a piece
		# 4 units away, etc.)
		for max_vision in range(1, 8):
			board.vision = board.calc_vision(initial=board.vision, max_vision=max_vision)
			# Generate 1 fake publickey
			# for each and every square
			pkeys = list(islice(fake_pk_gen, len(chess.SQUARES)))
			# But transmit a real publickey INSTEAD,
			# for each square we are entitled to view
			skeys = []
			for square in board.vision:
				sk, pk = make_real_keypair()
				skeys.append(sk)
				pkeys[square] = pk
			logging.debug('PEEK #%u: %s', max_vision, ','.join(chess.SQUARE_NAMES[square] for square in board.vision))
			query_response = self._send_peek_query(pkeys)
			# Only bother attempting decryption of
			# responses that correspond to squares
			# that we sent real publickeys for
			for square, sk in zip(board.vision, skeys):
				piece_data = pk_decrypt(sk, query_response[square])
				logging.debug('Decrypted %s at %i (%s)', piece_data, square, chess.SQUARE_NAMES[square])
				piece = chess.Piece.from_symbol(piece_data.decode()) if piece_data != b'\x00' else None
				if square in piece_map:
					assert piece_map[square] == piece, "Opponent sent contradictory information"
				else:
					piece_map[square] = piece
				if piece:
					board.set_piece_at(square, piece, gently=True)
		logging.info('PEEKED AT: %s', ','.join(chess.SQUARE_NAMES[square] for square in board.vision))
		return piece_map
	def _send_peek_query(self, pkeys):
		self._socket.send_serialized(pkeys, _serialize)
		return self._socket.recv_serialized(_deserialize)
	def notify_capture(self, square):
		self._socket.send_serialized(square, _serialize)
	def respond_to_peek(self, board, j=0):
		for i in range(7):
			pkeys = self._recv_peek_query()
			logging.debug('GOT QUERY #%i.%u.%u: %s', board.fullmove_number, j, i, ''.join(prettyprint_bytes(pk) for pk in pkeys))
			# Send an encrypted response with
			# the state of EVERY square we have
			# a piece on -- we will verify after
			# the match (TODO) that Alice sent
			# deterministically fake publickeys
			# for all squares not entitled to see
			response_payload = []
			for square, pk in zip(chess.SQUARES, pkeys):
				piece = board.piece_at(square)
				if piece and piece.color == self._color:
					piece_data = piece.symbol().encode()
				else:
					piece_data = b'\x00'
				encrypted_piece_data = pk_encrypt(pk, piece_data)
				response_payload.append(encrypted_piece_data)
			self._respond_peek_query(response_payload)
	def _recv_peek_query(self):
		pkeys = self._socket.recv_serialized(_deserialize)
		return pkeys
	def _respond_peek_query(self, payload):
		self._socket.send_serialized(payload, _serialize)
	def recv_capture_notify(self):
		square = self._socket.recv_serialized(_deserialize)
		return square

def _serialize(m):
	return [bencodepy.encode(m)]

def _deserialize(b):
	return bencodepy.decode(bytes().join(b))

def consume(iterator, n=None):
	"Advance the iterator n-steps ahead. If n is None, consume entirely."
	if n is None:
		deque(iterator, maxlen=0)
	else:
		next(islice(iterator, n, n), None)
