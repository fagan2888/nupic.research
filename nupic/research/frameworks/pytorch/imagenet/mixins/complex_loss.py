# ----------------------------------------------------------------------
# Numenta Platform for Intelligent Computing (NuPIC)
# Copyright (C) 2020, Numenta, Inc.  Unless you have an agreement
# with Numenta, Inc., for a separate license for this software code, the
# following terms and conditions apply:
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero Public License version 3 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU Affero Public License for more details.
#
# You should have received a copy of the GNU Affero Public License
# along with this program.  If not, see http://www.gnu.org/licenses.
#
# http://numenta.org/licenses/
# ----------------------------------------------------------------------

import time


class ComplexLoss(object):
    """
    Defines a new training loop that has direct access to Experiment attributes
    and can be customized for more complex loss functions
    """
    def train_epoch(self):
        """Overwrites train model to use private train_model method
        """
        self._train_model()

    def _train_model(self):
        """Private train model that has access to Experiment attributes
        """
        pre_batch_callback = self.pre_batch
        post_batch_callback = self.post_batch

        self.model.train()
        # Use asynchronous GPU copies when the memory is pinned
        # See https://pytorch.org/docs/master/notes/cuda.html
        async_gpu = self.train_loader.pin_memory

        # Check if training with Apex Mixed Precision
        # FIXME: There should be another way to check if 'amp' is enabled
        use_amp = hasattr(self.optimizer, "_amp_stash")
        try:
            from apex import amp
        except ImportError:
            if use_amp:
                raise ImportError(
                    "Mixed precision requires NVIDA APEX."
                    "Please install apex from https://www.github.com/nvidia/apex")

        t0 = time.time()
        for batch_idx, (data, target) in enumerate(self.train_loader):
            if batch_idx >= self.batches_in_epoch:
                break

            num_images = len(target)
            data = data.to(self.device, non_blocking=async_gpu)
            t1 = time.time()

            if pre_batch_callback is not None:
                pre_batch_callback(model=self.model, batch_idx=batch_idx)

            self.optimizer.zero_grad()

            loss, output = self.calculate_batch_loss(data, target, async_gpu=async_gpu)
            del output

            t2 = time.time()
            if use_amp:
                with amp.scale_loss(loss, self.optimizer) as scaled_loss:
                    scaled_loss.backward()
            else:
                loss.backward()

            t3 = time.time()
            self.optimizer.step()
            t4 = time.time()

            if post_batch_callback is not None:
                time_string = ("Data: {:.3f}s, forward: {:.3f}s, backward: {:.3f}s,"
                               + "weight update: {:.3f}s").format(t1 - t0, t2 - t1,
                                                                  t3 - t2, t4 - t3)
                post_batch_callback(model=self.model, loss=loss.detach(),
                                    batch_idx=batch_idx, num_images=num_images,
                                    time_string=time_string)
            del loss
            t0 = time.time()

    def calculate_batch_loss(self, data, target, async_gpu=True):
        """
        :param data: input to the training function, as specified by dataloader
        :param target: target to be matched by model, as specified by dataloader
        :param async_gpu: define whether or not to use
                          asynchronous GPU copies when the memory is pinned
        """
        output = self.model(data)
        target = target.to(self.device, non_blocking=async_gpu)
        loss = self.loss_function(output, target)

        del data, target
        return loss, output

    @classmethod
    def get_execution_order(cls):
        eo = super().get_execution_order()
        eo["train_epoch"] = ["ComplexLoss.train_epoch"]
        eo["_train_model"] = ["ComplexLoss._train_model"]
        eo["calculate_batch_loss"] = ["ComplexLoss.calculate_batch_loss"]
        return eo
