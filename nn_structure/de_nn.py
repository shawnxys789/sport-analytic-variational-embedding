import tensorflow as tf
from config.de_config import DECongfig


class DeterministicEmbedding():

    def __init__(self, config, is_probability):
        self.config = config
        self.is_probability = is_probability
        self.y_ph = tf.placeholder(dtype=tf.float32, shape=[None, None])
        self.embed_label_placeholder = tf.placeholder(dtype=tf.float32, shape=[None, None])
        self.trace_lengths_ph = tf.placeholder(dtype=tf.int32, shape=[None])
        self.rnn_input_ph = tf.placeholder(dtype=tf.float32, shape=[None, self.config.Learn.max_seq_length,
                                                                    self.config.Learn.feature_number])
        config = DECongfig
        self.dense_layer_bias = []
        self.dense_layer_weights = []
        self.lstm_cell_all = []
        self.embed_w = None
        self.embed_b = None

    def build(self):
        """
        define a shallow dynamic LSTM
        """
        # with tf.device('/gpu:0'):
        with tf.name_scope(self.config.Learn.model_type):
            with tf.name_scope("LSTM_layers"):
                for i in range(self.config.Arch.LSTM.lstm_layer_num):
                    self.lstm_cell_all.append(
                        tf.nn.rnn_cell.LSTMCell(num_units=self.config.Arch.LSTM.h_size, state_is_tuple=True,
                                                initializer=tf.random_uniform_initializer(-0.05, 0.05)))
            with tf.name_scope("Embed_layers"):
                self.embed_w = tf.get_variable('w_embed_home', [self.config.Arch.Encode.label_size,
                                                                self.config.Arch.Encode.latent_size],
                                               initializer=tf.contrib.layers.xavier_initializer())
                self.embed_b = tf.Variable(tf.zeros([self.config.Arch.Encode.latent_size]), name="b_embed_home")

            with tf.name_scope("Dense_layers"):
                for i in range(self.config.Arch.Dense.dense_layer_num):
                    w_input_size = self.config.Arch.LSTM.h_size + self.config.Arch.Encode.latent_size \
                        if i == 0 else self.config.Arch.Dense.hidden_node_size
                    w_output_size = self.config.Arch.Dense.hidden_node_size \
                        if i < self.config.Arch.Dense.dense_layer_num - 1 else self.config.Arch.Dense.output_layer_size
                    self.dense_layer_weights.append(tf.get_variable('w{0}_xaiver'.format(str(i)),
                                                                    [w_input_size, w_output_size],
                                                                    initializer=tf.contrib.layers.xavier_initializer()))
                    self.dense_layer_bias.append(tf.Variable(tf.zeros([w_output_size]), name="b_{0}".format(str(i))))

    def __call__(self):
        with tf.name_scope(self.config.Learn.model_type):
            with tf.name_scope("LSTM_layers"):
                rnn_output = None
                for i in range(self.config.Arch.LSTM.lstm_layer_num):
                    rnn_input = self.rnn_input_ph if i == 0 else rnn_output
                    rnn_output, rnn_state = tf.nn.dynamic_rnn(  # while loop dynamic learning rnn
                        inputs=rnn_input, cell=self.lstm_cell_all[i],
                        sequence_length=self.trace_lengths_ph, dtype=tf.float32,
                        scope=self.config.Learn.model_type + '_home_rnn_{0}'.format(str(i)))
                outputs = tf.stack(rnn_output)
                # Hack to build the indexing and retrieve the right output.
                self.batch_size = tf.shape(outputs)[0]
                # Start indices for each sample
                self.index = tf.range(0, self.batch_size) * self.config.Learn.max_seq_length + (
                            self.trace_lengths_ph - 1)
                # Indexing
                rnn_last = tf.gather(tf.reshape(outputs, [-1, self.config.Arch.LSTM.h_size]), self.index)

            with tf.name_scope("Embed_layers"):
                self.embed_layer = tf.matmul(self.embed_label_placeholder, self.embed_w) + self.embed_b

            # embed_layer = tf.concat([self.home_embed_layer, self.away_embed_layer], axis=1)
            # embed_layer = self.home_embed_layer

            with tf.name_scope('Dense_layers'):
                dense_output = None
                for i in range(self.config.Arch.Dense.dense_layer_num):
                    dense_input = tf.concat([self.embed_layer, rnn_last], axis=1) if i == 0 else dense_output
                    # dense_input = embed_layer
                    dense_output = tf.matmul(dense_input, self.dense_layer_weights[i]) + self.dense_layer_bias[i]
                    if i < self.config.Arch.Dense.dense_layer_num - 1:
                        dense_output = tf.nn.relu(dense_output, name='activation_{0}'.format(str(i)))

            if self.is_probability:
                self.read_out = tf.nn.softmax(dense_output)
                with tf.variable_scope('cross_entropy'):
                    self.cost = tf.losses.softmax_cross_entropy(onehot_labels=self.y_ph,
                                                                logits=dense_output)
            else:
                self.read_out = dense_output
                with tf.variable_scope('Norm2'):
                    self.cost = tf.reduce_mean(tf.square(self.read_out - self.y_ph))
            tf.summary.histogram('cost', self.cost)

            with tf.name_scope("train"):
                self.train_op = tf.train.AdamOptimizer(learning_rate=self.config.Learn.learning_rate).minimize(
                    self.cost)


if __name__ == '__main__':
    de_config_path = "../icehockey_de_config.yaml"
    cvrnn_config = DECongfig.load(de_config_path)
    DE = DeterministicEmbedding(config=cvrnn_config)
