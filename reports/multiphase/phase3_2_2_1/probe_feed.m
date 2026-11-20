paths={'C:/Users/86177/Desktop/work/archive/phase3_2_2_sensitivity/gas_order-coarse/plus-6d957192442706b3/input/INPUT_phase25.m';'C:/Users/86177/Desktop/work/archive/phase3_2_2_1_no_recovery/coarse/plus-ac2566001e7b488f/input/INPUT_phase25.m';'C:/Users/86177/Desktop/work/archive/phase3_2_2_1_no_recovery/coarse/minus-7a130cb1425ce766/input/INPUT_phase25.m';'C:/Users/86177/Desktop/work/archive/phase3_2_2_1_no_recovery/fine/plus-e24f1ffa1302b1a4/input/INPUT_phase25.m';'C:/Users/86177/Desktop/work/archive/phase3_2_2_1_no_recovery/fine/minus-3e11f4c6adc57fee/input/INPUT_phase25.m'};
values=zeros(length(paths),3);
converted=values;
for i=1:length(paths)
  lines=regexp(fileread(paths{i}),'(?m)^P_(H2|HNO|NO)_FROZ\s*=\s*([.0-9+eE-]+);','tokens');
  assert(numel(lines)==3)
  for j=1:3
    idx=find(strcmp(lines{j}{1},{'H2','HNO','NO'}));
    values(i,idx)=str2double(lines{j}{2});
    converted(i,idx)=str2double(num2str(values(i,idx)));
  end
end
save('pressure_probe.mat','values','converted','-v7')
