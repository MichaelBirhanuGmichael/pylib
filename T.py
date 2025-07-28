id_bytes = b' '


decimal_id = int.from_bytes(id_bytes, 'little')
print(f"The decoded ID is: {decimal_id}")

reconstructed_bytes = decimal_id.to_bytes(3, 'little')

formatted_bytes = ''.join(f'\\x{b:02x}' for b in reconstructed_bytes)
print(f"Reconstructed bytes: b'{formatted_bytes}'")
