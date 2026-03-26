import pickle

with open('results/election_anchors.pkl', 'rb') as f:
    data = pickle.load(f)

print(data['anchors']['2012'].keys())
