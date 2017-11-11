""" ========= LOSS FOR TRAIN ========= """

from tensorflow.python.framework import ops
from tensorflow.python.ops import math_ops
from tensorflow.python.ops import weights_broadcast_ops
from tensorflow.python.ops.losses import util

def compute_squared_distance_by_instance(labels, predictions):
  """compute the squared distance by instance
  input: labels, predictions
  return: a tensor of size (batch_size, )
  """
  # 경도 (y): 1도= 88.8km, 1분=1.48km, 1초≒25.0m (위도 37도 기준)
  # 위도 (x): 1도=111.0Km, 1분=1.85Km, 1초=30.8m
  # http://lovestudycom.tistory.com/entry/위도-경도-계산법
  unit = 100 # to prevent NanLossDuringTrainingError
  km_per_latitude, km_per_longitude = 111.0/unit, 88.8/unit
  squared_delta = math_ops.squared_difference(predictions, labels)
  weights = ops.convert_to_tensor([[km_per_latitude**2, km_per_longitude**2], ], 
                                  dtype=squared_delta.dtype)
  weights = weights_broadcast_ops.broadcast_weights(
      math_ops.to_float(weights), squared_delta)
  squared_rescaled = math_ops.multiply(squared_delta, weights)
  sum_of_squared_rescaled = math_ops.reduce_sum(squared_rescaled, 1)
  return sum_of_squared_rescaled * unit**2


def compute_mean_loss(losses, scope=None, 
                      loss_collection=ops.GraphKeys.LOSSES):
  """Computes the mean loss.
  """
  with ops.name_scope(scope, "mean_loss", (losses, )):
    losses = ops.convert_to_tensor(losses)
    input_dtype = losses.dtype
    losses = math_ops.to_float(losses)
    loss = math_ops.reduce_mean(losses)

    # Convert the result back to the input type.
    loss = math_ops.cast(loss, input_dtype)
    util.add_loss(loss, loss_collection)
    return loss


def mean_squared_distance_loss(labels, predictions, scope=None,
                               add_collection=False):
  """
  Adds a Mean-squared-distance loss to the training procedure.
  """
  if labels is None:
    raise ValueError("labels must not be None.")
  if predictions is None:
    raise ValueError("predictions must not be None.")
  with ops.name_scope(scope, "squared_distance_loss",
                      (predictions, labels)) as scope:
    predictions = math_ops.to_float(predictions)
    labels = math_ops.to_float(labels)
    predictions.get_shape().assert_is_compatible_with(labels.get_shape())

    squared_distances = compute_squared_distance_by_instance(predictions, labels)

    loss_collection = ops.GraphKeys.LOSSES if add_collection else None
    return compute_mean_loss(squared_distances, scope, loss_collection=loss_collection)
