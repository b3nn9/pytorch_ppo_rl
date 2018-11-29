import gym
import os
import random
from itertools import chain

import numpy as np

import torch.nn.functional as F
import torch.nn as nn
import torch
import cv2

from model import *

import torch.optim as optim
from torch.multiprocessing import Pipe, Process

from collections import deque
from sklearn.utils import shuffle
#from utils import make_train_data, ActorAgent
from tensorboardX import SummaryWriter
from torch.distributions.categorical import Categorical

class CNNActorAgent(object):
    def __init__(
            self,
            num_step,
            gamma=0.99,
            lam=0.95,
            use_gae=True,
            use_cuda=False):
        self.model = CnnActorCriticNetwork()
        self.num_step = num_step
        self.gamma = gamma
        self.lam = lam
        self.use_gae = use_gae
        self.learning_rate = 0.00025
        self.epoch = 3
        self.clip_grad_norm = 0.5
        self.ppo_eps = 0.1
        self.batch_size = 32

        self.optimizer = optim.Adam(self.model.parameters(), lr=self.learning_rate)

        self.device = torch.device('cuda' if use_cuda else 'cpu')

        self.model = self.model.to(self.device)

    def get_action(self, state):
        state = torch.Tensor(state).to(self.device)
        state = state.float()
        policy, value = self.model(state)
        policy = F.softmax(policy, dim=-1).data.cpu().numpy()

        action = self.random_choice_prob_index(policy)

        return action

    @staticmethod
    def random_choice_prob_index(p, axis=1):
        r = np.expand_dims(np.random.rand(p.shape[1 - axis]), axis=axis)
        return (p.cumsum(axis=axis) > r).argmax(axis=axis)

    def forward_transition(self, state, next_state):
        state = torch.from_numpy(state).to(self.device)
        state = state.float()
        policy, value = self.model(state)

        next_state = torch.from_numpy(next_state).to(self.device)
        next_state = next_state.float()
        _, next_value = self.model(next_state)

        value = value.data.cpu().numpy().squeeze()
        next_value = next_value.data.cpu().numpy().squeeze()

        return value, next_value, policy

    def train_model(self, s_batch, target_batch, y_batch, adv_batch):
        s_batch = torch.FloatTensor(s_batch).to(self.device)
        target_batch = torch.FloatTensor(target_batch).to(self.device)
        y_batch = torch.LongTensor(y_batch).to(self.device)
        adv_batch = torch.FloatTensor(adv_batch).to(self.device)

        sample_range = np.arange(len(s_batch))
        with torch.no_grad():
            # for multiply advantage
            policy_old, value_old = self.model(s_batch)
            m_old = Categorical(F.softmax(policy_old, dim=-1))
            log_prob_old = m_old.log_prob(y_batch)

        for i in range(self.epoch):
            np.random.shuffle(sample_range)
            for j in range(int(len(s_batch) / self.batch_size)):
                
                sample_idx = sample_range[self.batch_size * j:self.batch_size * (j + 1)]
                policy, value = self.model(s_batch[sample_idx])
                m = Categorical(F.softmax(policy, dim=-1))
                log_prob = m.log_prob(y_batch[sample_idx])

                ratio = torch.exp(log_prob - log_prob_old[sample_idx])

                surr1 = ratio * adv_batch[sample_idx]
                surr2 = torch.clamp(
                    ratio,
                    1.0 - self.ppo_eps,
                    1.0 + self.ppo_eps) * adv_batch[sample_idx]

                actor_loss = -torch.min(surr1, surr2).mean()
                critic_loss = F.mse_loss(
                    value.sum(1), target_batch[sample_idx])

                self.optimizer.zero_grad()
                loss = actor_loss + critic_loss
                loss.backward()
                torch.nn.utils.clip_grad_norm_(
                    self.model.parameters(), self.clip_grad_norm)
                self.optimizer.step()

class MlpActorAgent(object):
    def __init__(
            self,
            input_size,
            output_size,
            num_step,
            gamma=0.99,
            lam=0.95,
            use_gae=True,
            use_cuda=False):

        self.input_size = input_size
        self.output_size = output_size
        self.model = MlpActorCriticNetwork(self.input_size, self.output_size)
        self.num_step = num_step
        self.gamma = gamma
        self.lam = lam
        self.use_gae = use_gae
        self.learning_rate = 0.00025
        self.epoch = 3
        self.clip_grad_norm = 0.5
        self.ppo_eps = 0.1
        self.batch_size = 32

        self.optimizer = optim.Adam(self.model.parameters(), lr=self.learning_rate)

        self.device = torch.device('cuda' if use_cuda else 'cpu')

        self.model = self.model.to(self.device)

    def get_action(self, state):
        state = torch.Tensor(state).to(self.device)
        state = state.float()
        policy, value = self.model(state)
        policy = F.softmax(policy, dim=-1).data.cpu().numpy()

        action = self.random_choice_prob_index(policy)

        return action

    @staticmethod
    def random_choice_prob_index(p, axis=1):
        r = np.expand_dims(np.random.rand(p.shape[1 - axis]), axis=axis)
        return (p.cumsum(axis=axis) > r).argmax(axis=axis)

    def forward_transition(self, state, next_state):
        state = torch.from_numpy(state).to(self.device)
        state = state.float()
        policy, value = self.model(state)

        next_state = torch.from_numpy(next_state).to(self.device)
        next_state = next_state.float()
        _, next_value = self.model(next_state)

        value = value.data.cpu().numpy().squeeze()
        next_value = next_value.data.cpu().numpy().squeeze()

        return value, next_value, policy

    def train_model(self, s_batch, target_batch, y_batch, adv_batch):
        s_batch = torch.FloatTensor(s_batch).to(self.device)
        target_batch = torch.FloatTensor(target_batch).to(self.device)
        y_batch = torch.LongTensor(y_batch).to(self.device)
        adv_batch = torch.FloatTensor(adv_batch).to(self.device)

        sample_range = np.arange(len(s_batch))
        with torch.no_grad():
            # for multiply advantage
            policy_old, value_old = self.model(s_batch)
            m_old = Categorical(F.softmax(policy_old, dim=-1))
            log_prob_old = m_old.log_prob(y_batch)

        for i in range(self.epoch):
            np.random.shuffle(sample_range)
            for j in range(int(len(s_batch) / self.batch_size)):
                
                sample_idx = sample_range[self.batch_size * j:self.batch_size * (j + 1)]
                policy, value = self.model(s_batch[sample_idx])
                m = Categorical(F.softmax(policy, dim=-1))
                log_prob = m.log_prob(y_batch[sample_idx])

                ratio = torch.exp(log_prob - log_prob_old[sample_idx])

                surr1 = ratio * adv_batch[sample_idx]
                surr2 = torch.clamp(
                    ratio,
                    1.0 - self.ppo_eps,
                    1.0 + self.ppo_eps) * adv_batch[sample_idx]

                actor_loss = -torch.min(surr1, surr2).mean()
                critic_loss = F.mse_loss(
                    value.sum(1), target_batch[sample_idx])

                self.optimizer.zero_grad()
                loss = actor_loss + critic_loss
                loss.backward()
                torch.nn.utils.clip_grad_norm_(
                    self.model.parameters(), self.clip_grad_norm)
                self.optimizer.step()
