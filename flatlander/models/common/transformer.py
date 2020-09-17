from typing import List

import tensorflow as tf

from flatlander.models.common.attention import MultiHeadAttention
from flatlander.models.common.positional_tree_encoding import ShivQuirkPositionalEncoding


class Transformer(tf.keras.layers.Layer):

    def get_config(self):
        pass

    def __init__(self, num_encoder_layers,
                 d_model,
                 num_heads,
                 encoder_layer_neurons,
                 hidden_layers: List[int],
                 dropout_rate=0.1,
                 out_dim=None,
                 use_cnn_decoding=False,
                 use_positional_encoding=True):
        super(Transformer, self).__init__()

        if hidden_layers is None:
            hidden_layers = [512, 512]

        self.use_positional_encoding = use_positional_encoding
        self.use_cnn_decoding = use_cnn_decoding
        self.num_outputs = out_dim

        self.encoder = Encoder(num_encoder_layers,
                               d_model,
                               num_heads,
                               encoder_layer_neurons,
                               dropout_rate,
                               use_positional_encoding)

        self.dropout_1 = tf.keras.layers.Dropout(dropout_rate)
        self.dropout_2 = tf.keras.layers.Dropout(dropout_rate)
        self.dropout_3 = tf.keras.layers.Dropout(dropout_rate)

        self.hidden_layers = [tf.keras.layers.Dense(neurons, activation="relu")
                              for neurons in hidden_layers]

        self.out = tf.keras.layers.Dense(self.num_outputs)
        self.flatten = tf.keras.layers.Flatten()

        if self.use_cnn_decoding:
            self.conv_1 = tf.keras.layers.Conv1D(64, activation="relu", kernel_size=3)
            self.conv_2 = tf.keras.layers.Conv1D(128, activation="relu", kernel_size=3)

        if use_positional_encoding:
            self.pos_encoding = ShivQuirkPositionalEncoding(d_model=d_model)

    def call(self, input, train_mode, encoder_mask, positional_encoding=None):
        if self.use_positional_encoding:
            positional_encoding = self.pos_encoding(positional_encoding)
        enc_output = self.encoder(input, train_mode, positional_encoding, encoder_mask=encoder_mask)

        x = enc_output
        if self.use_cnn_decoding:
            x = self.conv_1(x)
            x = self.conv_2(x)
            x = self.dropout_1(x, training=train_mode)
        x = self.flatten(x)

        for i in range(len(self.policy_layers)):
            x = self.policy_layers[i](x)
        x = self.dropout_2(x, training=train_mode)
        out = self.policy(x)

        return out


class Encoder(tf.keras.layers.Layer):
    def __init__(self,
                 num_layers,
                 d_model,
                 num_heads,
                 dense_neurons,
                 rate=0.1,
                 use_positional_encoding=True,
                 embed_observations=False):
        super(Encoder, self).__init__()
        self.use_positional_encoding = use_positional_encoding
        self.d_model = d_model
        self.embed_observations = embed_observations
        self.num_layers = num_layers
        self.embedding_out = tf.keras.layers.Dense(d_model, activation="relu")

        self.enc_layers = [EncoderLayer(d_model, num_heads, dense_neurons, rate=rate)
                           for _ in range(num_layers)]

        self.dropout = tf.keras.layers.Dropout(rate)

    def call(self, x, training, positional_encoding, encoder_mask):

        if self.use_positional_encoding or self.embed_observations:
            x = self.embedding_out(x)

        if self.use_positional_encoding:
            x += positional_encoding

        x = self.dropout(x, training=training)

        for i in range(self.num_layers):
            x = self.enc_layers[i](x, training, encoder_mask)

        return x  # (batch_size, input_seq_len, d_model)


class EncoderLayer(tf.keras.layers.Layer):
    def __init__(self, d_model, num_heads, dense_neurons, use_residual=True, rate=0.1):
        super(EncoderLayer, self).__init__()
        self.use_residual = use_residual
        self.mha = MultiHeadAttention(d_model, num_heads, learn_scale=True)
        self.ffn = self.point_wise_feed_forward_network(d_model, dense_neurons)

        self.layer_norm_1 = tf.keras.layers.LayerNormalization(epsilon=1e-6)
        self.layer_norm_2 = tf.keras.layers.LayerNormalization(epsilon=1e-6)

        self.dropout_1 = tf.keras.layers.Dropout(rate)
        self.dropout_2 = tf.keras.layers.Dropout(rate)

    def call(self, x, training, mask):
        attn_output, _ = self.mha(x, x, x, mask)  # (batch_size, input_seq_len, d_model)
        attn_output = self.dropout_1(attn_output, training=training)
        if self.use_residual:
            out1 = self.layer_norm_1(attn_output + x)  # (batch_size, input_seq_len, d_model)
        else:
            out1 = self.layer_norm_1(attn_output)  # (batch_size, input_seq_len, d_model)

        ffn_output = self.ffn(out1)  # out1)  # (batch_size, input_seq_len, d_model)
        ffn_output = self.dropout_2(ffn_output, training=training)

        if self.use_residual:
            out2 = self.layer_norm_2(ffn_output + out1)  # out1)  # (batch_size, input_seq_len, d_model)
        else:
            out2 = self.layer_norm_2(ffn_output)  # (batch_size, input_seq_len, d_model)

        return out2

    @staticmethod
    def point_wise_feed_forward_network(d_model, dense_neurons):
        return tf.keras.Sequential([
            tf.keras.layers.Dense(dense_neurons, activation='relu'),
            tf.keras.layers.Dense(d_model)
        ])
