from .base_critic import BaseCritic
import torch
import torch.optim as optim
from torch.nn import utils
from torch import nn

from deeprl.infrastructure import pytorch_util as ptu


class DQNCritic(BaseCritic):
    def __init__(self, hparams, optimizer_spec, **kwargs):
        super().__init__(**kwargs)
        self.env_name = hparams["env_name"]
        self.ob_dim = hparams["ob_dim"]

        if isinstance(self.ob_dim, int):
            self.input_shape = (self.ob_dim,)
        else:
            self.input_shape = hparams["input_shape"]

        self.ac_dim = hparams["ac_dim"]
        self.double_q = hparams["double_q"]
        self.grad_norm_clipping = hparams["grad_norm_clipping"]
        self.gamma = hparams["gamma"]

        self.optimizer_spec = optimizer_spec
        network_initializer = hparams["q_func"]
        self.q_net = network_initializer(self.ob_dim, self.ac_dim)
        self.q_net_target = network_initializer(self.ob_dim, self.ac_dim)
        self.optimizer = self.optimizer_spec.constructor(
            self.q_net.parameters(), **self.optimizer_spec.optim_kwargs
        )
        self.learning_rate_scheduler = optim.lr_scheduler.LambdaLR(
            self.optimizer,
            self.optimizer_spec.learning_rate_schedule,
        )
        self.loss = nn.SmoothL1Loss()  # AKA Huber loss
        self.q_net.to(ptu.device)
        self.q_net_target.to(ptu.device)

    def update(self, ob_no, ac_na, next_ob_no, reward_n, terminal_n):
        """
        Update the parameters of the critic.
        let sum_of_path_lengths be the sum of the lengths of the paths sampled from
            Agent.sample_trajectories
        let num_paths be the number of paths sampled from Agent.sample_trajectories
        arguments:
            ob_no: shape: (sum_of_path_lengths, ob_dim)
            next_ob_no: shape: (sum_of_path_lengths, ob_dim). The observation after taking one step forward
            reward_n: length: sum_of_path_lengths. Each element in reward_n is a scalar containing
                the reward for each timestep
            terminal_n: length: sum_of_path_lengths. Each element in terminal_n is either 1 if the episode ended
                at that timestep of 0 if the episode did not end
        returns:
            nothing
        """
        ob_no = ptu.from_numpy(ob_no)
        ac_na = ptu.from_numpy(ac_na).to(torch.long)
        next_ob_no = ptu.from_numpy(next_ob_no)
        reward_n = ptu.from_numpy(reward_n)
        terminal_n = ptu.from_numpy(terminal_n)

        qa_t_values = self.q_net(ob_no)
        q_t_values = torch.gather(qa_t_values, 1, ac_na.unsqueeze(1)).squeeze(1)

        if self.double_q:
            """
            TODO: In double Q-learning, the best action is selected using the
            current Q-network, but the Q-value for this action
            is obtained from the target Q-network. See page 5 of
            https://arxiv.org/pdf/1509.06461.pdf for more details.
            """
            next_qa_t_values = torch.gather(
                self.q_net_target(next_ob_no), 1, self.q_net(next_ob_no).argmax(1).unsqueeze(1)
            ).squeeze(1)
            """
            END CODE
            """
        else:
            """
            TODO: compute the value of of the next state
            """
            next_qa_t_values = self.q_net_target(next_ob_no).max(dim=1)[0]
            """
            END CODE
            """

        """
        TODO: Compute the target values, remember to make sure no gradients
        are passed through the target values.
        Hint: Use torch.no_grad or .detach() to ensure no gradients are passed.
        """
        target = (reward_n + self.gamma * next_qa_t_values * (1 - terminal_n)).detach()
        """
        END CODE
        """

        assert q_t_values.shape == target.shape
        loss = self.loss(q_t_values, target)

        # Updates Q function to minimize bellman error
        # Includes gradient clipping for stability
        self.optimizer.zero_grad()
        loss.backward()
        utils.clip_grad_value_(self.q_net.parameters(), self.grad_norm_clipping)
        self.optimizer.step()

        return {
            "Training Loss": ptu.to_numpy(loss),
        }

    def update_target_network(self):
        """
        Copies parameters from the current Q function to the target.
        """
        for target_param, param in zip(
            self.q_net_target.parameters(), self.q_net.parameters()
        ):
            target_param.data.copy_(param.data)

    def qa_values(self, obs):
        obs = ptu.from_numpy(obs)
        qa_values = self.q_net(obs)
        return ptu.to_numpy(qa_values)
