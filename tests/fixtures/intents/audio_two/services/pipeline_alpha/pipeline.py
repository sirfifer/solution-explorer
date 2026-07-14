"""Primary audio pipeline implementation."""


class AudioPipeline:
    """Decodes, resamples, and mixes audio frames."""

    def process(self, frames):
        decoded = [self._decode(f) for f in frames]
        return self._mix(decoded)

    def _decode(self, frame):
        return frame

    def _mix(self, decoded):
        return decoded
