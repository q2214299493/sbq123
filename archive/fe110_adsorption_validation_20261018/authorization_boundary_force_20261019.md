# Explicit authority: three exact-structure GPU force comparisons

User request: 利用已完成的三个静态标签，比较原始 AQCat25 与微调模型在实际偏离结构上的逐原子力误差

Separate authorization question: 完成三结构公平比较还需在 MZ73 新运行一次受限 GPU 力预测：原始 AQCat25 和冻结2185各预测3个结构，仅推理，不训练、不松弛、不提交VASP。是否授权？

User answer: 授权运行这一个受限预测批次

Date:2026-10-19 Asia/Shanghai.
Scope: original AQCat25 and frozen2185,each on the unchanged POSCARs for
06C_before_003,06C_after_004,06C_final_057;VASP9896148/9896149/9896150.
One private MZ73 GPU1 batch,at most600seconds;no CPU fallback,no training,
optimization,checkpoint replacement,new VASP,old-job mutation or automatic retry.
Results return to work for exact-input/force/error review;not model promotion
or accepted adsorption energies. The existing16heldout exclusions and24untrained
frames remain unchanged.
