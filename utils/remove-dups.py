#!/usr/bin/env python3

import sys
import argparse

def embedd(dataset):
  return dataset.compute_embeddings(model)

def run_simularity(args):
  import fiftyone as fo
  import fiftyone.zoo as foz
  from sklearn.metrics.pairwise import cosine_similarity
  import numpy as np

  dataset = fo.load_dataset(args.dataset)

  model_name = "mobilenet-v2-imagenet-torch"

  model = foz.load_zoo_model(model_name)
  embeddings = dataset.compute_embeddings(model)
  print(embeddings.shape)

  similarity_matrix = cosine_similarity(embeddings)
  print(similarity_matrix.shape)
  sims = similarity_matrix - np.identity(len(similarity_matrix))

  for idx, sample in enumerate(dataset):
    max_similarity = sims[idx].max()
    sample["max_similarity"] = max_similarity
    sample.save()

  print("Max similarity saved to dataset. Check the app for the changes")

def launch_app(args):
  import fiftyone as fo
  dataset = fo.load_dataset(args.dataset)
  session = fo.launch_app(dataset, remote=True) 
  session.wait()

def rename_dataset(args):
  import fiftyone as fo
  dataset = fo.load_dataset(args.name)
  dataset.name = args.new_name
  dataset.save()

  print("Renamed to", args.new_name)

def load_cvat_dataset(args):
  import fiftyone as fo
  dataset = fo.Dataset.from_dir(args.data_dir, name=args.name,
      type=fo.types.CVATImageDataset)

  dataset.persistent = True

  print(dataset)
  print(dataset.head())

def main():
  parser = argparse.ArgumentParser(description='Load dataset and help remove near duplicates')
  subp = parser.add_subparsers()

  load_p = subp.add_parser('load')
  load_p.add_argument('-n', '--name', default=None)
  load_p.add_argument('data_dir')
  load_p.set_defaults(func=load_cvat_dataset)

  rename_p = subp.add_parser('rename')
  rename_p.add_argument('name', help='The previously loaded dataset name')
  rename_p.add_argument('new_name', help='The new name for the dataset')
  rename_p.set_defaults(func=rename_dataset)

  launch_p = subp.add_parser('launch', help='Launch the fiftyone app. Will wait until session is closed.')
  launch_p.add_argument('dataset', help='The dataset name that was loaded previously')
  launch_p.set_defaults(func=launch_app)

  run_sim_p = subp.add_parser('run_simul', help='Runs the simularity check on the specified loaded dataset.')
  run_sim_p.add_argument('dataset', help='The dataset name that was loaded previously')
  run_sim_p.set_defaults(func=run_simularity)

  args = parser.parse_args()
  args.func(args)

main()
